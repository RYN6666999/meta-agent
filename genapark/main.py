from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def root():
    return {"message": "genapark MCP server is running."}
