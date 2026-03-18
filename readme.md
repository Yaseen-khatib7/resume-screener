# Resume Screening System

A resume screening application that ranks resumes against a job description using semantic similarity, skill extraction, explainable matching, and ranking evaluation.

## Features

- Upload a job description and multiple resumes
- Rank candidates using semantic similarity and skill matching
- Show matched skills, missing required skills, and missing preferred skills
- Generate explainable candidate reports
- Auto-label resumes for evaluation
- Compare SBERT baseline vs fine-tuned model
- Evaluate ranking quality using NDCG@K
- Restore last uploaded batch using session-based storage
- React frontend for HR usability
- FastAPI backend for model inference and APIs

## Tech Stack

### Frontend
- React
- TypeScript
- CSS

### Backend
- FastAPI
- Uvicorn
- Python

### ML / NLP
- Sentence-BERT (SBERT)
- Fine-tuned embedding model
- Semantic similarity
- Skill extraction
- NDCG evaluation
