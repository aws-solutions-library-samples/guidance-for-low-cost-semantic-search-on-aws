"""
STORE_CHUNK_DYNAMO function:
This function gets triggered when the process of chunking finishes.
This function will scan two folders (chunks1000 and chunks2000)
It will take all the files inside those folders, calculate the vector embedding with bedrock embeddings v2
And write the chunks with the vectors in the respective dynamodb table

Important Note:
DynamoDB writes may take long time. Set timeout as long as feasible

Input:
{
  "statusCode": "200",
  "body": "Success",
  "chunk_Size": "[a, b]",
  "amount_chunks": "[x, y]",
  "Output": "s3://chunks_path"
}

Output:
If the job is ended correctly, it will return the following JSON
{
  "statusCode": "200",
  "chunks_small_written": "x",
  "chunks_big_written": "y"
}
If the job fails, it will return the following JSON
{
    'statusCode': 500,
}

"""

import json
import boto3
import os
from decimal import Decimal

# Initialize AWS clients
s3 = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')
bedrock_runtime = boto3.client('bedrock-runtime')

# DynamoDB table names from environment variables
DYNAMODB_TABLE_TEXTRACT = os.environ['DYNAMO_TABLE_TEXTRACT']
DYNAMODB_TABLE_LLM = os.environ['DYNAMO_TABLE_LLM']
CHUNK_SIZE = os.environ.get('CHUNK_SIZE', '1000')

def get_embedding(text: str) -> list:
    response = bedrock_runtime.invoke_model(
        modelId='amazon.titan-embed-text-v2:0',
        contentType='application/json',
        accept='application/json',
        body=json.dumps({'inputText': text})
    )
    embedding = json.loads(response['body'].read())['embedding']
    return embedding

def store_in_dynamodb(table_name: str, text_chunk: str, embedding: list, filename: str, group, _uuid):
    # TODO the item structure needs to change, we are going to use hash compession for faster query
    # key will be a vector hash prefix, and the sortKey will be a full hash
    # other indexes will help getting the file_path + chunks that should be unique
    # another hash will be the congnito group that it belongs to.
    # this will require an entire DynamoDb Vector managment lib that we will implement soon
    table = dynamodb.Table(table_name)
    decimal_embedding = json.dumps([value for value in embedding])
    table.put_item(
        Item={
            'id': f'{group}-{_uuid}',
            'filename': filename,
            'group': group,
            'vector': decimal_embedding,
            'text': text_chunk
        }
    )

def extract_filename_from_s3_path(s3_path):
    return s3_path.split('/')[-2]  # Get the second to last element after splitting

def process_file(bucket, key, table_name, origin_filename, base_prefix):
    response = s3.get_object(Bucket=bucket, Key=key)
    content = response['Body'].read().decode('utf-8')
    
    embedding = get_embedding(content)
    
    # Construct the full filename including the origin filename and internal path
    relative_path = key[len(base_prefix):]
    full_filename = f"{origin_filename}/{relative_path.lstrip('/')}"
    group = base_prefix.split('/')[1]
    _uuid = base_prefix.split('/')[2].split('_')[0]
    
    store_in_dynamodb(table_name, content, embedding, full_filename,group,_uuid)

def process_folder(bucket, prefix, table_name, origin_filename, base_prefix):
    processed_files = 0
    next_token = None
    response = s3.list_objects_v2(Bucket=bucket, Prefix=prefix)
    while True:
        if response.get('IsTruncated', False): next_token = response['NextContinuationToken']
        else: next_token = None
        for obj in response.get('Contents', []):
            key = obj['Key']
            process_file(bucket, key, table_name, origin_filename, base_prefix)
            processed_files += 1
        # get next page
        if next_token:
            response = s3.list_objects_v2(Bucket=bucket, Prefix=prefix, ContinuationToken=next_token)
        else:
            break
    return processed_files

def handler(event, context):
    s3_path = event["Payload"]['Output']
    
    # Extract origin filename from S3 path
    origin_filename = extract_filename_from_s3_path(s3_path)
    
    # Extract bucket and prefix from S3 path
    parts = s3_path.replace("s3://", "").split("/")
    bucket = parts[0]
    base_prefix = "/".join(parts[1:])
    # if the s3path has _raw_llm use DYNAMODB_TABLE_LLM else DYNAMODB_TABLE_TEXTRACT
    if parts[-2].endswith("_llm"):
        DYNAMODB_TABLE = DYNAMODB_TABLE_LLM
    else:
        DYNAMODB_TABLE = DYNAMODB_TABLE_TEXTRACT
    # Process chunks1000 folder
    chunks_prefix = os.path.join(base_prefix, f"chunks{CHUNK_SIZE}/")
    processed_files = process_folder(bucket, chunks_prefix, DYNAMODB_TABLE, origin_filename, base_prefix)
    
    # Process chunks2000 folder
    # chunks2000_prefix = os.path.join(base_prefix, f"chunks{CHUNK_SIZE}/")
    # processed_files_2000 = process_folder(bucket, chunks2000_prefix, DYNAMODB_TABLE_LLM, origin_filename, base_prefix)
    
    return {
        "statusCode": "200",
        f"chunks_{CHUNK_SIZE}_written": str(processed_files),
        "table": DYNAMODB_TABLE
    }