# Procurement Agent – Business Analytics Capstone

This repository contains the PostgreSQL star schema and supporting datasets
for the Procurement Agent project.

The database powers analytics on:

- Commodity prices
- Producer Price Index (PPI)
- Tariff schedules
- Supplier & product relationships
- Country-level risk indicators

---

## Repository Structure

```
procurement_agent/
│
├── cleaned_data/        # Cleaned CSV files used for staging
├── sql/                 # All database DDL + load scripts
│   ├── load/            # Scripts that must be run in order
│   ├── drafts/          # Scratch / experimental SQL
│   ├── dimensions.sql   # Dimension table DDL
│   ├── facts.sql        # Fact table DDL
│   └── README.md        # Database setup instructions
│
└── README.md            # Project overview (this file)
```

---

## Database Setup

All instructions for loading and running the PostgreSQL database
are located in:
 - sql/README.md


Follow that document step-by-step to:

1. Create the database
2. Run staging scripts and data definition scripts for dimension and fact tables
3. Load dimensions
4. Load facts
5. Begin querying

---

## Important

The scripts must be run **in the correct order**.
Running them out of order will cause foreign key errors.

See `sql/README.md` for exact commands.