FROM timwarr/python3.11-talib 

# Set the working directory to /app
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY . /app

# Install dependencies from requirements.txt
RUN pip install -r requirements.txt

# Run python when the container launches
CMD ["python", "./start.py"]
