import os

# Function to read the configuration from the config.txt file
def load_config(file_path="config.txt"):
    config = {}
    with open(file_path, "r") as f:
        for line in f:
            name, value = line.strip().split("=")
            config[name] = value
    return config