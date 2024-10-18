# Databricks notebook source
# MAGIC %pip install -U --quiet databricks-sdk==0.29.0 langchain-core==0.2.24 databricks-vectorsearch==0.40 langchain-community==0.2.10 typing-extensions==4.12.2 youtube_search Wikipedia grandalf mlflow==2.14.3 pydantic==2.8.2
# MAGIC
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

from langchain_community.chat_models import ChatDatabricks

# You can play with max_tokens to define the length of the response
llm_llama = ChatDatabricks(endpoint="databricks-meta-llama-3-1-70b-instruct", max_tokens = 500)

for chunk in llm_llama.stream("Who is Brad Pitt?"):
    print(chunk.content, end="\n", flush=True)

# COMMAND ----------


