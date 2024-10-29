# Databricks notebook source
# MAGIC %load_ext autoreload
# MAGIC %autoreload 2
# MAGIC # Enables autoreload; learn more at https://docs.databricks.com/en/files/workspace-modules.html#autoreload-for-python-modules
# MAGIC # To disable autoreload; run %autoreload 0

# COMMAND ----------

# MAGIC %pip install typing_extensions>=4.5 --upgrade

# COMMAND ----------

# MAGIC %pip install -r requirements.txt

# COMMAND ----------

from main2 import main
main()

# COMMAND ----------

restartPython()

# COMMAND ----------


