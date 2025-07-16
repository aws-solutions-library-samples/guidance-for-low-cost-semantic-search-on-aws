#!/usr/bin/env python3
import os

import aws_cdk as cdk

from chatbot.chatbot_stack import ChatbotStack
from chatbot.waf_stack import WafStack

app = cdk.App()

# Deploy WAF in us-east-1 (required for CloudFront)
waf_stack = WafStack(app, "WafStack", 
    env=cdk.Environment(
        account=os.environ["CDK_DEFAULT_ACCOUNT"],
        region="us-east-1"),
    cross_region_references=True,
    description="Guidance for Low Cost Semantic search on AWS (5179), (SO9030) WAF in us-east-1")

# Deploy main stack in the default region
main_stack = ChatbotStack(app, "ChatbotStack",
    env=cdk.Environment(
        account=os.environ["CDK_DEFAULT_ACCOUNT"],
        region=os.environ["CDK_DEFAULT_REGION"]),
    cross_region_references=True,
    waf_acl_arn=waf_stack.waf_acl_arn,
    description="Guidance for Low Cost Semantic search on AWS (5179), (SO9030)")

app.synth()
