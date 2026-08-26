# Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.
# Proprietary software — see LICENSE in the repository root.
# https://zyvor.dev · info@zyvor.dev

"""OpenAPI specification for hyper2kvm Worker API."""

from __future__ import annotations

OPENAPI_SPEC = {
    "openapi": "3.0.3",
    "info": {
        "title": "hyper2kvm Worker API",
        "version": "0.3.0",
        "description": "REST API for hyper2kvm migration workers. Manages jobs, health checks, and capabilities.",
        "license": {"name": "Apache-2.0"},
    },
    "paths": {
        "/healthz": {
            "get": {
                "summary": "Health check",
                "operationId": "healthCheck",
                "tags": ["health"],
                "responses": {
                    "200": {
                        "description": "Worker is healthy",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "status": {"type": "string", "example": "healthy"},
                                        "active_jobs": {"type": "integer", "example": 0},
                                    },
                                }
                            }
                        },
                    }
                },
            }
        },
        "/readyz": {
            "get": {
                "summary": "Readiness check",
                "operationId": "readinessCheck",
                "tags": ["health"],
                "responses": {
                    "200": {
                        "description": "Worker is ready to accept jobs",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "status": {"type": "string", "enum": ["ready", "not_ready"]},
                                        "active_jobs": {"type": "integer"},
                                    },
                                }
                            }
                        },
                    },
                    "503": {"description": "Worker not ready"},
                },
            }
        },
        "/api/v1/jobs": {
            "get": {
                "summary": "List migration jobs",
                "operationId": "listJobs",
                "tags": ["jobs"],
                "parameters": [
                    {
                        "name": "status",
                        "in": "query",
                        "schema": {"type": "string", "enum": ["pending", "running", "completed", "failed"]},
                    },
                    {
                        "name": "limit",
                        "in": "query",
                        "schema": {"type": "integer", "default": 50, "maximum": 200},
                    },
                    {"name": "offset", "in": "query", "schema": {"type": "integer", "default": 0}},
                ],
                "responses": {
                    "200": {
                        "description": "Job list",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "jobs": {
                                            "type": "array",
                                            "items": {"$ref": "#/components/schemas/Job"},
                                        },
                                        "total": {"type": "integer"},
                                    },
                                }
                            }
                        },
                    }
                },
            },
            "post": {
                "summary": "Submit a migration job",
                "operationId": "submitJob",
                "tags": ["jobs"],
                "requestBody": {
                    "required": True,
                    "content": {"application/json": {"schema": {"$ref": "#/components/schemas/JobSpec"}}},
                },
                "responses": {
                    "202": {"description": "Job accepted"},
                    "400": {"description": "Invalid job spec"},
                    "429": {"description": "Too many concurrent jobs"},
                },
            },
        },
        "/api/v1/jobs/{job_id}": {
            "get": {
                "summary": "Get job status",
                "operationId": "getJob",
                "tags": ["jobs"],
                "parameters": [
                    {"name": "job_id", "in": "path", "required": True, "schema": {"type": "string"}}
                ],
                "responses": {
                    "200": {
                        "description": "Job details",
                        "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Job"}}},
                    },
                    "404": {"description": "Job not found"},
                },
            },
            "delete": {
                "summary": "Cancel a job",
                "operationId": "cancelJob",
                "tags": ["jobs"],
                "parameters": [
                    {"name": "job_id", "in": "path", "required": True, "schema": {"type": "string"}}
                ],
                "responses": {
                    "200": {"description": "Job cancelled"},
                    "404": {"description": "Job not found"},
                    "409": {"description": "Job already completed"},
                },
            },
        },
        "/api/v1/capabilities": {
            "get": {
                "summary": "Worker capabilities",
                "operationId": "getCapabilities",
                "tags": ["worker"],
                "responses": {
                    "200": {
                        "description": "Worker capability report",
                        "content": {
                            "application/json": {"schema": {"$ref": "#/components/schemas/Capabilities"}}
                        },
                    }
                },
            }
        },
    },
    "components": {
        "schemas": {
            "Job": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "status": {
                        "type": "string",
                        "enum": ["pending", "queued", "running", "completed", "failed"],
                    },
                    "progress": {"type": "number", "minimum": 0, "maximum": 100},
                    "source": {"type": "string"},
                    "output": {"type": "string"},
                    "error": {"type": "string"},
                    "created_at": {"type": "string", "format": "date-time"},
                    "started_at": {"type": "string", "format": "date-time"},
                    "completed_at": {"type": "string", "format": "date-time"},
                },
            },
            "JobSpec": {
                "type": "object",
                "required": ["source"],
                "properties": {
                    "source": {"type": "string", "description": "Path or URL to source disk"},
                    "output_dir": {"type": "string"},
                    "out_format": {"type": "string", "enum": ["qcow2", "raw", "vdi"], "default": "qcow2"},
                    "compress": {"type": "boolean", "default": True},
                    "fstab_mode": {
                        "type": "string",
                        "enum": ["stabilize-all", "bypath-only", "noop"],
                        "default": "stabilize-all",
                    },
                    "regen_initramfs": {"type": "boolean", "default": True},
                },
            },
            "Capabilities": {
                "type": "object",
                "properties": {
                    "worker_id": {"type": "string"},
                    "backends": {"type": "array", "items": {"type": "string"}},
                    "formats": {"type": "array", "items": {"type": "string"}},
                    "nbd_available": {"type": "boolean"},
                    "lvm_available": {"type": "boolean"},
                    "max_concurrent_jobs": {"type": "integer"},
                    "cpu_count": {"type": "integer"},
                    "memory_gb": {"type": "number"},
                },
            },
        },
        "securitySchemes": {
            "bearerAuth": {
                "type": "http",
                "scheme": "bearer",
                "description": "Token from HYPER2KVM_API_TOKEN env var",
            }
        },
    },
}


def get_spec_json() -> str:
    """Return the OpenAPI spec as JSON string."""
    import json

    return json.dumps(OPENAPI_SPEC, indent=2)


def get_spec_yaml() -> str:
    """Return the OpenAPI spec as YAML string."""
    import yaml

    return yaml.dump(OPENAPI_SPEC, default_flow_style=False, sort_keys=False)
