FROM c15-engine-runner:20261101
RUN python -m pip install --no-cache-dir --index-url https://pypi.org/simple svix==2.9.1
