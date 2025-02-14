# For more information, please refer to https://aka.ms/vscode-docker-python
FROM gurobi/python

# Keeps Python from generating .pyc files in the container
ENV PYTHONDONTWRITEBYTECODE=1

# Turns off buffering for easier container logging
ENV PYTHONUNBUFFERED=1

# Install dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Required for installing FZI packages
    git \
    # GLPK solver
    glpk-utils \
    # Required for pytest
    tk \
    && rm -rf /var/lib/apt/lists/*
    

# Install pip requirements
COPY requirements.txt .
RUN python -m pip install --no-cache-dir -r requirements.txt

WORKDIR /app
ENV PYTHONPATH=src

# During debugging, this entry point will be overridden. For more information, please refer to https://aka.ms/vscode-docker-python-debug
ENTRYPOINT [ "tests/docker/entrypoint.sh", "--cov-report", "term", "--cov=src", "tests/" ]
