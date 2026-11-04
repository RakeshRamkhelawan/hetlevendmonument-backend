# Error Handling Documentation

## Overview

This document describes the error handling strategy for the SanskritiSetu platform.

## HTTP Status Codes

- `400` - Bad Request: Invalid input data
- `401` - Unauthorized: Authentication required
- `403` - Forbidden: Insufficient permissions
- `404` - Not Found: Resource does not exist
- `422` - Unprocessable Entity: Validation error
- `500` - Internal Server Error: Unexpected server error

## Exception Hierarchy

- `SanskritiSetuException` - Base exception for all platform errors
- `TenantNotFoundError` - Tenant isolation errors
- `AuthenticationError` - Authentication failures
- `ValidationError` - Input validation errors

## Middleware

Exception handlers are registered in `src.core.exceptions.handlers` and applied
via `register_exception_handlers(app)` during application startup.
