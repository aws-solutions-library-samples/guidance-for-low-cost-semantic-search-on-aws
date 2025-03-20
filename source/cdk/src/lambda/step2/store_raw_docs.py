"""
STORE_RAW_DOCS function:
This function is responsible for reading the textract originated JSON
It parses the file and builds a raw text file from the text contents of the JSON
It then writes the output to the raw_text folder in the upload bucket

Input:
{
    'statusCode': 200,
    'JobID': job_id,
    'Output': "s3://{upload_bucket}/{json_path}"
}

Output:
If the job is ended correctly, it will return the following JSON
{
    'statusCode': 200,
    'Output': "s3://{upload_bucket}/{text_upload_path}"
}
If the job fails, it will return the following JSON
{
    'statusCode': 400,
    'Output': 'Error: Previous job was not successful'
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

"""

import boto3
import json

# Initialize S3 client
s3 = boto3.client('s3')
#upload the same file to bucket in folder raw_json
def upload_to_s3(bucket, key, content):
    s3.put_object(Bucket=bucket, Key=key, Body=content)


def handler(event, context):

    # print("Event",event)
    # Parse the input from the first Lambda function
    input_data = event["Payload"]
    
    # Check if the status is successful
    if input_data['statusCode'] != 200:
        return {
            'statusCode': 400,
            'Output': 'Error: Previous job was not successful'
        }
    
    # Extract the S3 path of the JSON file
    s3_path = input_data['Output']
    bucket = s3_path.split('/')[2]
    key = '/'.join(s3_path.split('/')[3:])
    file_extension = key.split('.')[-1].lower()
    key_name_with_extension = key.split('/')[-1]

    #if file extension is .txt just upload_to_s3 and return success
    if file_extension == 'txt':
        key_txt = f"raw_text/{key_name_with_extension}"
        upload_to_s3(bucket, key_txt, event['detail']['object']['content'])
        return { 'statusCode': 200,
            'Output': f"s3://{bucket}/{key_txt}"} 

    # Read the JSON file from S3
    response = s3.get_object(Bucket=bucket, Key=key)
    json_content = json.loads(response['Body'].read().decode('utf-8'))
    
    # Extract raw text from the JSON
    raw_text = ""
    for page in json_content['Pages']:
        for block in page['Blocks']:
            if block['BlockType'] == 'LINE':
                raw_text += block['Text'] + "\n"
    
    # Create a filename for the text output
    # Remove the existing aws_request_id and add the new one
    filename_parts = key.split('/')[-1].split('_')
    if len(filename_parts) > 2:
        original_filename = '_'.join(filename_parts[:-1])  # Skip the last part (_textract)
    else:
        original_filename = filename_parts[0]  # In case there was no old request_id
    
    group = key.split('/')[-2]
    txt_filename = f"raw_text/{group}/{original_filename}_raw.txt"
    
    # Upload the text file to S3
    s3.put_object(
        Bucket=bucket,
        Key=txt_filename,
        Body=raw_text.encode('utf-8')
    )
    
    # print(f"Raw text extracted and saved to {txt_filename}")
    
    # Prepare the output
    file_output = f"s3://{bucket}/{txt_filename}"
    
    return {
        'statusCode': 200,
        'Output': file_output
    }
