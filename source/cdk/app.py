#!/usr/bin/env python3
import os

import aws_cdk as cdk

from chatbot.chatbot_stack import ChatbotStack


app = cdk.App()
ChatbotStack(app, "ChatbotStack",env=cdk.Environment(
    account = os.environ["CDK_DEFAULT_ACCOUNT"],
    region = os.environ["CDK_DEFAULT_REGION"]),
    description = "Guidance for Low Cost Semantic search on AWS (5179)")

app.synth()
