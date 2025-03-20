import boto3
import logging
import json
import os
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)
s3Client = boto3.client('s3')
class TextConsolidator:
    def __init__(self, region="us-east-1"):
        self.s3_client = s3Client

    def get_raw_text_key(self, prefix):
        """Convert the processed files prefix to raw text key"""
        # Remove the trailing underscore if present
        if prefix.endswith('_'):
            prefix = prefix[:-1]
            
        # Replace pages_processed with raw_text and add _raw.txt
        if 'pages_processed/' in prefix:
            new_key = prefix.replace('pages_processed/', 'raw_text/', 1)
            # Remove any page number patterns (e.g., page_1, page_2)
            base_key = '_'.join(new_key.split('_')[:-2]) if 'page_' in new_key else new_key
            return f"{base_key}_raw_llm.txt"
        return prefix

    def list_matching_files(self, bucket, prefix):
        """List all files matching the prefix pattern"""
        try:
            paginator = self.s3_client.get_paginator('list_objects_v2')
            matching_files = []
            
            # Ensure the prefix ends with underscore for exact matching
            if not prefix.endswith('_'):
                prefix = prefix + '_'

            for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
                if 'Contents' in page:
                    for obj in page['Contents']:
                        if obj['Key'].endswith('.txt'):
                            matching_files.append(obj['Key'])
            
            matching_files.sort()  # Sort to maintain page order
            logger.info(f"Found {len(matching_files)} matching files")
            return matching_files
            
        except ClientError as e:
            logger.error(f"Error listing files: {str(e)}")
            raise

    def consolidate_files(self, input_data):
        """Consolidate multiple text files into a single raw text file"""
        try:
            # Extract bucket and prefix from input
            bucket = os.environ.get('BUCKET_NAME', None)
            prefix = input_data['Prefix']
            # replace "pages" with "pages_processed" in preffix
            prefix = prefix.replace("pages", "pages_processed")
            
            logger.info(f"Processing files with prefix: {prefix} in bucket: {bucket}")

            # Get list of matching files
            matching_files = self.list_matching_files(bucket, prefix)
            
            if not matching_files:
                raise ValueError(f"No matching files found for prefix: {prefix}")

            # Consolidate content from all files
            consolidated_text = []
            for file_key in matching_files:
                logger.info(f"Reading file: {file_key}")
                response = self.s3_client.get_object(Bucket=bucket, Key=file_key)
                content = response['Body'].read().decode('utf-8')
                consolidated_text.append(content)
                logger.info(f"Added content from: {file_key}")

            # Join all text with double newlines
            final_text = '\n\n'.join(consolidated_text)

            # Generate output key
            output_key = self.get_raw_text_key(prefix)
            
            # Save consolidated text to S3
            self.s3_client.put_object(
                Bucket=bucket,
                Key=output_key,
                Body=final_text.encode('utf-8'),
                ContentType='text/plain'
            )

            logger.info(f"Successfully consolidated and saved to: {bucket}/{output_key}")

            return {
                'bucket': bucket,
                'input_prefix': prefix,
                'output_key': output_key,
                'files_processed': len(matching_files),
                'status': 'success'
            }

        except Exception as e:
            logger.error(f"Error consolidating files: {str(e)}")
            raise

def main():
    """
    Test function with hardcoded values
    """
    # Initialize consolidator
    consolidator = TextConsolidator()

    # Simulation of step functions input format (with hardcoded values)
    step_functions_input = {
        "InitialInput": {
            "detail": {
                "bucket": {
                    "name": "jmgm-knowledgebases"
                }
            }
        },
        "Map": {
            "Item": {
                "Value": {
                    "Prefix": "pages_processed/group1/41a89fc5-a188-4cdf-95e1-23a635869bc1_test_"
                }
            }
        }
    }

    try:
        # Test with Step Functions format
        print("\nTesting with Step Functions input format...")
        step_functions_formatted_input = {
            "Bucket": step_functions_input["InitialInput"]["detail"]["bucket"]["name"],
            "Prefix": step_functions_input["Map"]["Item"]["Value"]["Prefix"]
        }
        result = consolidator.consolidate_files(step_functions_formatted_input)
        print(f"Processing complete. Result: {json.dumps(result, indent=2)}")

    except Exception as e:
        print(f"An error occurred: {str(e)}")

def handler(event, context):
    logger.info("Received event: " + json.dumps(event, indent=2))
    consolidator = TextConsolidator()
    result = consolidator.consolidate_files(event)
    return result