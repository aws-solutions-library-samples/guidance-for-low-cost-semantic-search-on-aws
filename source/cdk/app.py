#!/usr/bin/env python3
import os

import aws_cdk as cdk

from chatbot.chatbot_stack import ChatbotStack


app = cdk.App()
ChatbotStack(app, "ChatbotStack")

app.synth()
