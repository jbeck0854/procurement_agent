# PostgreSQL Star Schema – Setup & Load Instructions

This document explains how to create and load the Procurement Agent database locally.

Follow these steps exactly.

---

# 1️ Prerequisites

You must have:

- PostgreSQL installed
- `psql` available in your terminal
- Access to create a database

Verify installation:

```bash
psql --version
```
---

# 2 Create the Database

You may use your own username and password.

Example (recommended clean setup):

```bash
psql -U postgres
```

Inside psql:

```SQL
CREATE DATABASE procurement_agent;
\q
```

# 3 Run Scripts in Correct Order

IMPORTANT:
Run all commands from the project root directory (procurement_agent) for following steps to work properly.

e.g., :
```bash
cd procurement_agent
```

Step 1 - Create Staging Tables
```bash
psql -U postgres -d procurement_agent -f sql/load/stage.sql
```

Step 2 - Load CSV Data into Staging Tables
```bash
psql -U postgres -d procurement_agent -f sql/load/copy_staging.sql
```

STEP 3 - Create Dimension Tables
```bash
psql -U postgres -d procurement_agent -f sql/dimensions.sql
```

Step 4 - Populate Dimensions
```bash
psql -U postgres -d procurement_agent -f sql/load/load_dimensions.sql
```

Step 5 - Create Fact Tables
```bash
psql -U postgres -d procurement_agent -f sql/facts.sql
```

Step 6 - Populate Fact Tables
```bash
psql -U postgres -d procurement_agent -f sql/load/load_facts.sql
```

# 4 Verify the Load

Connect:
```bash
psql -U postgres -d procurement_agent
```

List tables:
```SQL
\dt
```

Check row counts e.g., :
```SQL
SELECT COUNT(*) FROM dim_product;
```

Exit:
```SQL
\q
```

# 5 Reset Database (If Needed)

```bash
psql -U postgres
```

```SQL
DROP DATABASE procurement_agent;
CREATE DATABASE procurement_agent;
\q
```

Then rerun the load steps.

---