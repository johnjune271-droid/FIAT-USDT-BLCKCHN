fnfcu-receiver/
├── app/
│   ├── main.py          # FastAPI endpoint
│   ├── validator.py     # Section 5,7 rules
│   ├── idempotency.py   # Section 9
│   ├── profiles.py      # Your Receiver Profile - Section 6
│   ├── settlement.py    # Async worker
│   └── models.py        # DB models
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env