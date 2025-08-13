import boto3
import json
import logging
import os
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

class PDFProcessor:
    def __init__(self, region="us-east-1"):
        self.s3_client = boto3.client('s3')
        self.bedrock_runtime = boto3.client(
            service_name='bedrock-runtime',
            region_name=region
        )
        self.MODEL_ID = "anthropic.claude-3-haiku-20240307-v1:0"

    def get_processed_key(self, original_key):
        """Convert the original key to the processed key path"""
        # Replace 'pages' with 'pages_processed' and change extension to .txt
        if 'pages/' in original_key:
            new_key = original_key.replace('pages/', 'pages_processed/', 1)
            new_key = os.path.splitext(new_key)[0] + '.txt'
            return new_key
        return original_key

    def get_pdf_from_s3(self, bucket, key):
        """Download PDF from S3"""
        try:
            response = self.s3_client.get_object(Bucket=bucket, Key=key)
            pdf_bytes = response['Body'].read()
            logger.info(f"PDF size: {len(pdf_bytes) / 1024 / 1024:.2f} MB")
            return pdf_bytes
        except Exception as e:
            logger.error(f"Error downloading PDF: {str(e)}")
            raise

    def process_pdf_with_claude(self, bucket, key):
        """Process PDF directly with Claude 3 using converse API"""
        try:
            # Need to download the PDF as bytes since 'uri' is not supported
            logger.info(f"Downloading PDF from S3: {bucket}/{key}")
            pdf_bytes = self.get_pdf_from_s3(bucket, key)
            
            doc_message = {
                "role": "user",
                "content": [
                    {
                        "document": {
                            "name": "Document 1",
                            "format": "pdf",
                            "source": {
                                "bytes": pdf_bytes  # Must use bytes, not URI
                            }
                        }
                    },
                    {
                        "text": "You are a document text extractor. Your task is to extract text from this PDF maintaining the original format as much as possible. Follow these rules:\n\n1. Extract ALL text from the PDF\n2. Preserve the original layout, including tables and bullet points\n3. Include ALL numbers, dates, and special characters\n4. Maintain text alignment (left, right, center) when evident\n5. Preserve paragraph breaks and spacing\n6. For tables: maintain column alignment and use proper spacing\n7. Include headers, footers, and page numbers if present\n8. Keep any formatting like bullet points or numbered lists\n9. Do not add any explanations or comments\n10. Do not describe the PDF or its contents\n11. Output ONLY the extracted text\n\nExtract the content from an image page and output in Markdown syntax. Enclose the content in the <markdown></markdown> tag and do not use code blocks. If the image is empty then output a <markdown></markdown> without anything in it.\nFollow these steps:\nExamine the provided page carefully.\nIdentify all elements present in the page, including headers, body text, footnotes, tables, images, captions, and page numbers, etc.\nUse markdown syntax to format your output:\nHeadings: # for main, ## for sections, ### for subsections, etc.\nLists: * or - for bulleted, 1. 2. 3. for numbered\nDo not repeat yourself\nIf the element is an image (not table)\nIf the information in the image can be represented by a table, generate the table containing the information of the image\nOtherwise provide a detailed description about the information in image\nClassify the element as one of: Chart, Diagram, Logo, Icon, Natural Image, Screenshot, Other. Enclose the class in <figure_type></figure_type>\nEnclose <figure_type></figure_type>, the table or description, and the figure title or caption (if available), in <figure></figure> tags\nDo not transcribe text in the image after providing the table or description\nIf the element is a table\nCreate a markdown table, ensuring every row has the same number of columns\nMaintain cell alignment as closely as possible\nDo not split a table into multiple tables\nIf a merged cell spans multiple rows or columns, place the text in the top-left cell and output ' ' for other\nUse | for column separators, |-|-| for header row separators\nIf a cell has multiple items, list them in separate rows\nIf the table contains sub-headers, separate the sub-headers from the headers in another row\nIf the element is a paragraph\nTranscribe each text element precisely as it appears\nIf the element is a header, footer, footnote, page number\nTranscribe each text element precisely as it appears"
                    }
                ]
            }

            logger.info("Sending PDF to Claude for processing...")
            response = self.bedrock_runtime.converse(
                modelId=self.MODEL_ID,
                messages=[doc_message],
                inferenceConfig={
                    "maxTokens": 4096,
                    "temperature": 0
                }
            )

            extracted_text = response['output']['message']['content'][0]['text']

            # Log token usage
            token_usage = response['usage']
            logger.info(f"Input tokens: {token_usage['inputTokens']}")
            logger.info(f"Output tokens: {token_usage['outputTokens']}")
            logger.info(f"Total tokens: {token_usage['totalTokens']}")
            logger.info(f"Stop reason: {response['stopReason']}")

            # Print raw output for debugging
            logger.info("Raw output from Claude (first 500 chars):")
            logger.info("-" * 50)
            logger.info(extracted_text[:500] + "..." if len(extracted_text) > 500 else extracted_text)
            logger.info("-" * 50)

            # Clean up memory
            del pdf_bytes
            
            return extracted_text

        except ClientError as e:
            error_message = e.response['Error']['Message']
            logger.error(f"Error processing with Claude: {error_message}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in process_pdf_with_claude: {str(e)}")
            raise

    def process_document(self, input_data):
        """Process PDF document with the new input structure"""
        try:
            # Extract bucket and key from input
            bucket = input_data['Bucket']
            key = input_data['Key']
            
            logger.info(f"Processing document from bucket: {bucket}, key: {key}")

            # Process PDF directly from S3
            extracted_text = self.process_pdf_with_claude(bucket, key)

            # Generate output key
            output_key = self.get_processed_key(key)
            
            # Save processed text to S3
            self.s3_client.put_object(
                Bucket=bucket,
                Key=output_key,
                Body=extracted_text.encode('utf-8'),
                ContentType='text/plain'
            )

            logger.info(f"Successfully processed and saved to: {bucket}/{output_key}")

            return {
                'bucket': bucket,
                'input_key': key,
                'output_key': output_key,
                'status': 'success'
            }

        except Exception as e:
            logger.error(f"Error processing document: {str(e)}")
            raise

def handler(event, context):
    logger.info("Received event: " + json.dumps(event, indent=2))
    # get the default lambda region
    region = os.environ.get('AWS_DEFAULT_REGION', 'us-east-1')
    pdf_processor = PDFProcessor(region=region)
    result = pdf_processor.process_document(event)
    return result