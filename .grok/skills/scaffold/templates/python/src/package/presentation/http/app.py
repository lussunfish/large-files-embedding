from fastapi import FastAPI

app = FastAPI(title="{{PROJECT_NAME}}", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
