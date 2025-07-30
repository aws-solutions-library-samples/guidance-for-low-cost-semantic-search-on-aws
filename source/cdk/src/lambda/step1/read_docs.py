"""
READ_DOCS function:
This function gets triggered when a file is uploaded in the selected upload bucket.
It creates a textract job to extract the text from the PDF file
It then waits for the job to end and writes the result from the job as a JSON file
Within the same bucket, in the raw_json folder

Important Note:
Textract jobs may take long time. Set timeout as long as feasible

Input:
Standard S3 put event JSON

Output:
If the job is ended correctly, it will return the following JSON
{
    'statusCode': 200,
    'JobID': job_id,
    'Output': "s3://{upload_bucket}/{json_path}"
}
If the job fails, it will return the following JSON
{
    'statusCode': 500,
    'JobID': job_id,
    'Output': None
}

Permissions required in the lambda role:
S3: GET, PUT, LISTBUCKET permission, in the upload_bucket
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "VisualEditor0",
            "Effect": "Allow",
            "Action": [
                "s3:PutObject",
                "s3:GetObject",
                "s3:ListBucket"
            ],
            "Resource": "upload_bucket"
        }
    ]
}
Textract: StartDocumentTextDetection, GetDocumentTextDetection
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "VisualEditor0",
            "Effect": "Allow",
            "Action": [
                "textract:StartDocumentTextDetection",
                "textract:GetDocumentTextDetection"
            ],
            "Resource": "*"
        }
    ]
}

"""


import boto3
import json
import time
import os
import uuid
from pathlib import Path
import pypdf


# Initialize AWS clients
s3 = boto3.client('s3')
textract = boto3.client('textract')
dynamodb = boto3.resource('dynamodb')
ssm = boto3.client('ssm')
#upload the same file to bucket in folder raw_json
s3_resource = boto3.resource('s3')
sns_topic = os.environ.get("SNS_TOPIC", None)
sns_role = os.environ.get("TEXTRACT_ROLE", None)

def get_pdf_password():
    """
    Retrieve PDF password from SSM Parameter Store.
    
    Returns:
        str: The PDF password, or None if parameter doesn't exist
    """
    try:
        response = ssm.get_parameter(
            Name=os.environ.get('PDF_PASSWORD_PARAMETER','/workshop/pdf-processor/password'),
            WithDecryption=True
        )
        return response['Parameter']['Value']
    except ssm.exceptions.ParameterNotFound:
        print("PDF password parameter not found in SSM")
        return None
    except Exception as e:
        print(f"Error retrieving PDF password from SSM: {str(e)}")
        return None

def handle_encrypted_pdf(pdf_path: str) -> str:
    """
    Check if PDF is encrypted and decrypt if needed using SSM password.
    
    Args:
        pdf_path (str): Path to the PDF file
        
    Returns:
        str: Path to the decrypted PDF (or original if not encrypted)
        
    Raises:
        ValueError: If PDF is encrypted but cannot be decrypted
        RuntimeError: If PDF processing fails
    """
    try:
        with open(pdf_path, 'rb') as pdf_file:
            pdf_reader = pypdf.PdfReader(pdf_file)
            
            if pdf_reader.is_encrypted:
                print(f"PDF {pdf_path} is encrypted, attempting to decrypt...")
                
                # Get password from SSM
                password = get_pdf_password()
                if not password:
                    raise ValueError("PDF is encrypted but no password found in SSM parameter store")
                
                # Try to decrypt
                if not pdf_reader.decrypt(password):
                    raise ValueError("Failed to decrypt PDF with provided password")
                
                print("PDF successfully decrypted")
                
                # Create decrypted version
                pdf_writer = pypdf.PdfWriter(clone_from=pdf_reader)
                decrypted_path = pdf_path.replace('.pdf', '_decrypted.pdf')
                
                with open(decrypted_path, 'wb') as output_file:
                    pdf_writer.write(output_file)
                
                return decrypted_path
            
            print(f"PDF {pdf_path} is not encrypted")
            return pdf_path  # Not encrypted, return original
            
    except Exception as e:
        print(f"Error handling encrypted PDF: {str(e)}")
        raise RuntimeError(f"Failed to handle encrypted PDF: {str(e)}") from e

def copy_to_s3(bucket_source, bucket_target, key_source, key_target):
    #Creating S3 Resource From the Session.
    #create a source dictionary that specifies bucket name and key name of the object to be copied
    copy_source = {
        'Bucket': bucket_source,
        'Key': key_source
    }
    s3_resource.meta.client.copy(copy_source, bucket_target, key_target)

def create_document_dynamodb(key, bucket):
    head_object = s3.head_object(Bucket=bucket, Key=key)
    print(head_object)
    size = head_object['ContentLength']
    # transform size to KB
    size = str(size / 1024)
    # generate a UUID
    _uuid = str(uuid.uuid4())
    dynamodb.Table(os.environ.get("DOCUMENT_TABLE", "aibot-documents")).put_item(
        Item={
            'group': key.split('/')[-2],
            'filename': key.split('/')[-1],
            'uuid': _uuid,
            'size': size
        }
    )
    return _uuid

def split_pdf(pdf_path: str, output_dir: str = "split_pages") -> list[str]:
    """
    Splits a PDF into single pages and saves them in the output directory using pypdf.
    
    Args:
        pdf_path (str): Path to the PDF file to split
        output_dir (str): Directory where to save the individual pages
        
    Returns:
        list[str]: List of paths to the created PDF files
        
    Raises:
        FileNotFoundError: If PDF file doesn't exist
        RuntimeError: If PDF processing fails
    """
    try:
        # Validate input file exists
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")
            
        # Create output directory
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        created_files = []
        
        # Open and process PDF
        with open(pdf_path, 'rb') as pdf_file:
            pdf_reader = pypdf.PdfReader(pdf_file)
            
            for page_num in range(len(pdf_reader.pages)):
                # Create new PDF writer for each page
                pdf_writer = pypdf.PdfWriter()
                # Add the page
                pdf_writer.add_page(pdf_reader.pages[page_num])
                
                # Save the page
                output_path = str(output_dir / f"page_{page_num + 1}.pdf")
                with open(output_path, 'wb') as output_file:
                    pdf_writer.write(output_file)
                created_files.append(output_path)
                    
        return created_files
        
    except Exception as e:
        raise RuntimeError(f"Failed to split PDF: {str(e)}") from e

def handler(event, context):
    # print("Event",event)
    # Get bucket and object information from the event
    bucket = event['detail']['bucket']['name']
    key = event['detail']['object']['key']
    # get cognito group from the key of the bucket
    _uuid = create_document_dynamodb(key, bucket)
    #review file extension
    file_extension = key.split('.')[-1].lower()
    key_name_with_extension = key.split('/')[-1]

    #if file extension is .txt just copy_to_s3 and return success
    # TODO test this properly
    if file_extension == 'txt':
        key_txt = f"raw_json/{key_name_with_extension}"
        print(key_txt)
        copy_to_s3(bucket, bucket, key, key_txt)
        return { 'statusCode': 200,
            'JobID': 'txt, no textract job needed',
            'Output': f"s3://{bucket}/{key_txt}"} 
    
    # Download the PDF from S3 for processing
    local_file_name = key.split('/')[-1]
    local_file_name = f"/tmp/{local_file_name}"
    s3.download_file(bucket, key, local_file_name)
    
    # Handle encrypted PDFs
    try:
        processed_pdf_path = handle_encrypted_pdf(local_file_name)
        
        # If PDF was decrypted, upload the decrypted version to decrypted_raw/ folder
        if processed_pdf_path != local_file_name:
            # Replace raw_docs with decrypted_raw in the key
            decrypted_key = key.replace('raw_docs/', 'decrypted_raw/')
            s3.upload_file(processed_pdf_path, bucket, decrypted_key)
            textract_key = decrypted_key
            print(f"Uploaded decrypted PDF to: {decrypted_key}")
        else:
            textract_key = key
            
    except Exception as e:
        print(f"Error processing encrypted PDF: {str(e)}")
        return {
            'statusCode': 500,
            'JobID': None,
            'Output': None,
            'Error': f"Failed to process encrypted PDF: {str(e)}"
        }
    
    # Start Textract job using the appropriate key (original or decrypted)
    response = textract.start_document_text_detection(
        DocumentLocation={
            'S3Object': {
                'Bucket': bucket,
                'Name': textract_key
            }
        },
        NotificationChannel={
            'SNSTopicArn': sns_topic,
            'RoleArn': sns_role
        },
        ClientRequestToken=_uuid
    )
    
    # Split the PDF into pages using the processed (potentially decrypted) PDF
    output_dir = "/tmp/split_pages"
    original_filename = key.split('/')[-1].split('.')[0]
    group = key.split('/')[-2]
    key_filename_prefix = f"pages/{group}/{_uuid}_{original_filename}"
    
    try:
        for file in split_pdf(processed_pdf_path, output_dir):
            key_filename = f"{key_filename_prefix}_{file.split('/')[-1]}"
            s3.upload_file(file, bucket, key_filename)
    except Exception as e:
        print(f"Error splitting PDF: {str(e)}")
        return {
            'statusCode': 500,
            'JobID': response['JobId'],
            'Output': None,
            'Error': f"Failed to split PDF: {str(e)}"
        }
    
    # return the job id and the path of the key_filename_prefix
    return {
        'statusCode': 200,
        'JobID': response['JobId'],
        'pages_prefix': f"{key_filename_prefix}"
    }