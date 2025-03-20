"""
Lambda function that receives a document from an S3 bucket, processes the document,
creates chunks of the document, and stores each chunk in a different document in the same S3 bucket.

Execution role permission: The Lambda function needs permission to read and write to the specified S3 bucket.

JSON INPUT:
{
    'statusCode': 200,
    'Output': "s3://bucket_name/raw_text/key_input.txt"
}

JSON OUTPUT:
{
    'statusCode': 200,
    'body': 'Success',
    'Output': "s3://bucket_name/rag/key_input/",
    'chunk_Size': "[1000, 2000]",
    'amount_chunks': "[75, 33]"
}
"""

import boto3
import json
import os
from langchain_text_splitters import RecursiveCharacterTextSplitter
from urllib.parse import urlparse

s3 = boto3.client('s3')
DEFAULT_TMP = os.environ.get('DEFAULT_TMP')
def get_chunks(document, chunk_size, overlap):
    """
    Function to split the document into chunks based on the provided chunk_size and overlap.

    Args:
        document (str): The input document to be split into chunks.
        chunk_size (int): The maximum size of each chunk.
        overlap (int): The number of characters to overlap between consecutive chunks.

    Returns:
        tuple: A tuple containing two elements:
            - A list of `Document` objects representing the chunks.
            - The number of chunks created.
    """
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=overlap, length_function=len)
    docs = text_splitter.create_documents([document])
    return docs, len(docs)

def save_chunks_in_s3(chunks, bucket, key_prefix, chunk_size, file_name):
    """
    Function to save the document chunks to an S3 bucket.

    Args:
        chunks (list): A list of `Document` objects representing the chunks.
        bucket (str): The name of the S3 bucket.
        key_prefix (str): The prefix for the S3 object keys.
        chunk_size (int): The size of the chunks.
        file_name (str): The name of the input file.
    """
    for i, doc in enumerate(chunks, start=1):
        key = f'{key_prefix}/chunks{chunk_size}/chunk{i}'
        # print(f"Saving chunk {i} to {key}")
        s3.put_object(Body=doc.page_content, Bucket=bucket, Key=key)

def handler(event, context):
    """
    AWS Lambda handler function.

    Args:
        event (dict): The event data received by the Lambda function.
        context (object): The context object containing information about the Lambda execution environment.

    Returns:
        dict: A dictionary containing the response data.
    """

    # print("Event",event)
    # Check if the input URL is provided in the event data
    input_url = event["Payload"].get('Output')
    if not input_url:
        return {'statusCode': 400, 'body': json.dumps('Missing input URL')}

    # Parse the input URL to extract the S3 bucket name and object key
    parsed_url = urlparse(input_url)
    bucket = parsed_url.netloc
    key = parsed_url.path.lstrip('/')
    file_name = os.path.splitext(os.path.basename(key))[0]
    try:
        # Download the input file from S3 to a temporary file
        file_path = f'{DEFAULT_TMP}/{file_name}'
        with open(file_path, 'wb') as f:
            s3.download_fileobj(bucket, key, f)

        # Read the downloaded file content
        with open(file_path, 'r') as f:
            document = f.read()

    except Exception as e:
        # Return an error response if an exception occurs during file download or reading
        return {'statusCode': 500, 'body': json.dumps(f'Error: {e}')}

    # Define a list of chunk sizes to be used for splitting the document
    chunk_sizes = [1000, 2000]
    amount_chunks = []

    # Iterate over the chunk sizes
    for chunk_size in chunk_sizes:
        # Split the document into chunks based on the current chunk size and overlap
        chunks, num_chunks = get_chunks(document, chunk_size, 200)
        amount_chunks.append(num_chunks)

        # Save the chunks to the S3 bucket
        group = key.split('/')[-2]
        key_prefix = f'rag/{group}/{file_name}'
        save_chunks_in_s3(chunks, bucket, key_prefix, chunk_size, file_name)

    # Return a success response with the chunk sizes, number of chunks, and output S3 prefix
    return {
        'statusCode': str(200),
        'body': "Success",
        'chunk_Size': str(chunk_sizes),
        'amount_chunks': str(amount_chunks),
        'Output': f's3://{bucket}/{key_prefix}/',
    }