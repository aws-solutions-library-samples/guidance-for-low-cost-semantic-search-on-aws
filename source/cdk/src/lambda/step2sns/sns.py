import boto3
import json
import os
textract = boto3.client('textract')
dynamodb = boto3.resource('dynamodb')
sfn = boto3.client('stepfunctions')
table_name = os.environ.get('DOCUMENTS_TABLE_NAME', None)
bucket_name = os.environ.get('DOCUMENTS_BUCKET_NAME', None)
state_machine = os.environ.get('SATE_MACHINE', None)
s3 = boto3.client('s3')
def get_uuid_dynamo(key):
    # key : "raw_docs/group1/test.pdf"
    # group1 is the dynamo key
    # test.pdf is the file name and the filename sortkey in dynamo
    table = dynamodb.Table(table_name)
    response = table.get_item(
        Key={
            'group': key.split('/')[1],
            'filename': key.split('/')[-1]
        }
    )
    return response['Item']['uuid']


def handler(event, context):
    print("Event:", event)
    job_id = None
    status = None
    bucket = None
    key = None
    for record in event['Records']:
        message = json.loads(record['Sns']['Message'])
        print("Message:", message)
        job_id = message['JobId']
        status = message['Status']
        bucket = message['DocumentLocation']['S3Bucket']
        key = message['DocumentLocation']['S3ObjectName']
        _uuid = get_uuid_dynamo(key)
        print(f"Textract job {job_id} completed with status {status} UUID:{_uuid}")

    response = textract.get_document_text_detection(JobId=job_id)
    
    if status == 'SUCCEEDED':
        # Collect all pages
        pages = []
        pages.append(response)
        response = textract.get_document_text_detection(JobId=job_id)
        next_token = response.get('NextToken')
        
        while next_token:
            response = textract.get_document_text_detection(JobId=job_id, NextToken=next_token)
            pages.append(response)
            next_token = response.get('NextToken')
        
        # Combine all pages into a single JSON
        full_response = {
            'JobId': job_id,
            'Status': status,
            'Pages': pages
        }
        
        # Create a filename for the JSON output, including the aws_request_id
        original_filename = key.split('/')[-1].split('.')[0]
        group = key.split('/')[-2]
        json_filename = f"raw_json/{group}/{_uuid}_{original_filename}_textract.json"
        
        # Upload the JSON to S3
        s3.put_object(
            Bucket=bucket,
            Key=json_filename,
            Body=json.dumps(full_response)
        )
        
        # print(f"Textract job completed. Output saved to {json_filename}")
        # Trigger state Machine
        sfn.start_execution(
            stateMachineArn=state_machine,
            input=json.dumps({
                "Payload": {
                    "Output": f"s3://{bucket}/{json_filename}",
                    "statusCode": 200
                }
            })
        )
        return {
            'statusCode': 200,
            'JobID': job_id,
            'Output': f"s3://{bucket}/{json_filename}"
        }
    else:
        # print(f"Textract job failed for {key}")
        return {
            'statusCode': 500,
            'JobID': job_id,
            'Output': None
        }