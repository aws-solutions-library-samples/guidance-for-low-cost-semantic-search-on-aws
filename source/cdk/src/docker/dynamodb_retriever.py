from typing import List

from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
# TODO add numpy and scipy into the requirements
import numpy as np
from scipy.spatial.distance import cosine
import boto3
import os
import json

class DynamoDBRetriever(BaseRetriever):
    #documents: List[Document]
    """List of documents to retrieve from."""
    #k: int
    """Number of top results to return"""
    #tolerance: float
    """Maximum cosine similarity to consider a match"""
    target_table: str
    group_id: str
    def __init__(self,**kwargs) -> None:
        super().__init__(**kwargs)
        self.target_table = kwargs.get('target_table', "DYNAMO_TABLE_TEXTRACT")
        self.group_id = kwargs.get('group_id', "default")
        #print("group_id_init", self.group_id)

    def _get_relevant_documents(self, query: str, *, run_manager: CallbackManagerForRetrieverRun) -> List[Document]:
        dynamodb = boto3.client('dynamodb')
        table_name = os.environ.get(self.target_table)
        query_embedding = self.query_to_embedding(query)
        if self.group_id:
            paginator = dynamodb.get_paginator('query')
            _kargs = {
                'KeyConditionExpression': '#grp = :group_id',
                'ExpressionAttributeValues': {
                    ':group_id': {'S': self.group_id}
                },
                'ExpressionAttributeNames': {
                    '#grp': 'group'
                },
                'TableName': table_name,
                'IndexName': 'group',
                'PaginationConfig': {'PageSize': os.environ.get("DYNAMO_PAGE_SIZE", 20)}
            }
        else:
            paginator = dynamodb.get_paginator('scan')
            _kargs = {
                'TableName': table_name,
                'PaginationConfig': {'PageSize': os.environ.get("DYNAMO_PAGE_SIZE", 20)}
            }
        
        response_iterator = paginator.paginate(**_kargs)
        tolerance = float(os.environ.get('TOLERANCE', "0.3"))
        similarities = []
        for page in response_iterator:
            for item in page['Items']:
                similarity = self.calculate_similarity(query_embedding, item['vector']['S'])
                if similarity >= tolerance:
                    similarities.append((similarity, item['text']['S']))
        # print("similarities", similarities)
        documents = [Document(page_content=chunk, metadata={"similarity": similarity}) for similarity, chunk in sorted(similarities, reverse=True)]
        # print("documents", documents)
        return documents
    
    def calculate_similarity(self, query_embedding, document_embedding):
        # print(document_embedding)
        # print('query_embedding',query_embedding)
        # print("Document embedding", json.loads(document_embedding))
        return 1 - cosine(query_embedding, json.loads(document_embedding))
    
    def query_to_embedding(self, query: str) -> List[float]:
        bedrock = boto3.client('bedrock-runtime')
        model_id = os.environ.get('EMBEDDING_MODEL_ID', "amazon.titan-embed-text-v2:0")
        # get the embedding for the query
        response = bedrock.invoke_model(
            modelId=model_id,
            contentType='application/json',
            accept='application/json',
            body=json.dumps({'inputText': query})
        )
        embedding = json.loads(response['body'].read())['embedding']
        return embedding