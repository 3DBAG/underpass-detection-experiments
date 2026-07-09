# Underpass Detection 2D

Detect underpass geometries by comparing BAG and BGT building polygons using
2D spatial operations.

This is a Python implementation of the SQL pipeline from
[`detection_2d/sql/underpasses.sql`](../detection_2d/sql/underpasses.sql).

## Installation

```bash
uv pip install -e .
```

## Configuration

```bash
cp .env.example .env
```

Edit `.env` with your database credentials.

## Usage

```bash
python scripts/detect_underpasses.py
```
