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
import pymupdf


# Initialize S3 and Textract clients
s3 = boto3.client('s3')
textract = boto3.client('textract')
dynamodb = boto3.resource('dynamodb')
#upload the same file to bucket in folder raw_json
s3_resource = boto3.resource('s3')
sns_topic = os.environ.get("SNS_TOPIC", None)
sns_role = os.environ.get("TEXTRACT_ROLE", None)
DEFAULT_TMP = os.environ.get('DEFAULT_TMP')

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
    Splits a PDF into single pages and saves them in the output directory.
    
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
        with pymupdf.open(pdf_path) as pdf_document:
            for page_num in range(len(pdf_document)):
                # Create new PDF with single page
                with pymupdf.open() as new_pdf:
                    new_pdf.insert_pdf(pdf_document, from_page=page_num, to_page=page_num)
                    
                    # Save the page
                    output_path = str(output_dir / f"page_{page_num + 1}.pdf")
                    new_pdf.save(output_path)
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
    response = textract.start_document_text_detection(
        DocumentLocation={
            'S3Object': {
                'Bucket': bucket,
                'Name': key
            }
        },
        NotificationChannel={
            'SNSTopicArn': sns_topic,
            'RoleArn': sns_role
        },
        ClientRequestToken=_uuid
    )
    # Split the doc into pages
    # download the pdf from s3
    local_file_name = key.split('/')[-1]
    # download has to be in the tmp dir
    local_file_name = f"{DEFAULT_TMP}/{local_file_name}"
    output_dir = f"{DEFAULT_TMP}/split_pages"
    s3.download_file(bucket, key, local_file_name)
    # upload to s3
    original_filename = key.split('/')[-1].split('.')[0]
    group = key.split('/')[-2]
    key_filename_prefix = f"pages/{group}/{_uuid}_{original_filename}"
    for file in split_pdf(local_file_name, output_dir):
        key_filename = f"{key_filename_prefix}_{file.split('/')[-1]}"
        s3.upload_file(file, bucket, key_filename)
    # return the job id and the path of the key_filename_prefix
    return {
        'statusCode': 200,
        'JobID': response['JobId'],
        'pages_prefix': f"{key_filename_prefix}"
    }

    # TODO Return and do not wait we will subscribe to the textract SNS
    # Get the job ID
    # job_id = response['JobId']
    
    # # print(f"Started Textract job {job_id} for {key}")
    
    # # Wait for the job to complete
    # while True:
    #     response = textract.get_document_text_detection(JobId=job_id)
    #     status = response['JobStatus']
    #     if status in ['SUCCEEDED', 'FAILED']:
    #         break
    #     time.sleep(5)
    
    # if status == 'SUCCEEDED':
    #     # Collect all pages
    #     pages = []
    #     pages.append(response)
    #     next_token = response.get('NextToken')
        
    #     while next_token:
    #         response = textract.get_document_text_detection(JobId=job_id, NextToken=next_token)
    #         pages.append(response)
    #         next_token = response.get('NextToken')
        
    #     # Combine all pages into a single JSON
    #     full_response = {
    #         'JobId': job_id,
    #         'Status': status,
    #         'Pages': pages
    #     }
        
    #     # Create a filename for the JSON output, including the aws_request_id
    #     original_filename = key.split('/')[-1].split('.')[0]
    #     group = key.split('/')[-2]
    #     json_filename = f"raw_json/{group}/{_uuid}_{original_filename}_textract.json"
        
    #     # Upload the JSON to S3
    #     s3.put_object(
    #         Bucket=bucket,
    #         Key=json_filename,
    #         Body=json.dumps(full_response)
    #     )
        
    #     # print(f"Textract job completed. Output saved to {json_filename}")
        
    #     return {
    #         'statusCode': 200,
    #         'JobID': job_id,
    #         'Output': f"s3://{bucket}/{json_filename}"
    #     }
    # else:
    #     # print(f"Textract job failed for {key}")
    #     return {
    #         'statusCode': 500,
    #         'JobID': job_id,
    #         'Output': None
    #     }