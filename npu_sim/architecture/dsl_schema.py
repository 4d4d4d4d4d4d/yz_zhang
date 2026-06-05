"""JSON Schema for the architecture DSL.

Mirror of SPEC-003 §4 with v0.2 mapping_hints tightening (D2).
"""

from __future__ import annotations

# Pattern allowed for module ids and port names: snake_case starting with a letter.
_NAME = r"^[a-z][a-z0-9_]*$"
_MODULE_PORT = r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$"

DSL_SCHEMA: dict = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "required": ["schema_version", "name"],
    "properties": {
        "schema_version": {"type": "string", "pattern": r"^[0-9]+\.[0-9]+$"},
        "name": {"type": "string", "minLength": 1},
        "description": {"type": "string"},
        "metadata": {
            "type": "object",
            "properties": {
                "author": {"type": "string"},
                "created": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
            },
        },
        "base": {"type": "string"},
        "overrides": {"$ref": "#/definitions/Overrides"},
        "clock_domains": {
            "type": "array",
            "items": {"$ref": "#/definitions/ClockDomain"},
        },
        "modules": {
            "type": "array",
            "items": {"$ref": "#/definitions/ModuleInstance"},
        },
        "connections": {
            "type": "array",
            "items": {"$ref": "#/definitions/Connection"},
        },
        "topology": {"$ref": "#/definitions/Topology"},
        "constraints": {"$ref": "#/definitions/Constraints"},
        "mapping_hints": {"$ref": "#/definitions/MappingHints"},
    },
    "oneOf": [
        {"required": ["modules", "connections"]},
        {"required": ["base"]},
    ],
    "definitions": {
        "ClockDomain": {
            "type": "object",
            "required": ["id", "period_ps"],
            "properties": {
                "id": {"type": "string", "pattern": _NAME},
                "period_ps": {"type": "integer", "minimum": 1},
                "skew_ps": {"type": "integer", "default": 0},
            },
        },
        "ModuleInstance": {
            "type": "object",
            "required": ["id", "type"],
            "properties": {
                "id": {"type": "string", "pattern": _NAME},
                # Module type follows IModule MODULE_TYPE_REGEX (validated at
                # Elaborator semantic phase, not by JSON Schema, so that
                # registration errors give a cleaner message).
                "type": {"type": "string"},
                "clock": {"type": "string", "pattern": _NAME},
                "config": {"type": "object"},
            },
        },
        "Connection": {
            "type": "object",
            "required": ["from", "to"],
            "properties": {
                "from": {"type": "string", "pattern": _MODULE_PORT},
                "to": {"type": "string", "pattern": _MODULE_PORT},
                "fifo_depth": {"type": "integer", "minimum": 1, "default": 1},
                "latency_cycles": {"type": "integer", "minimum": 0, "default": 1},
                "bandwidth_gbps": {"type": "number", "minimum": 0},
            },
        },
        "Overrides": {
            "type": "object",
            "properties": {
                "modules": {
                    "type": "object",
                    "additionalProperties": {
                        "type": "object",
                        "properties": {
                            "config": {"type": "object"},
                            "clock": {"type": "string", "pattern": _NAME},
                            "__relocate__": {
                                # SPEC-003 v1.1 §2.2: relocate a module across
                                # dies / domains by injecting estimate_*
                                # multipliers. Does not touch ports / type /
                                # capabilities.
                                "type": "object",
                                "properties": {
                                    "from_die": {"type": ["string", "integer"]},
                                    "to_die": {"type": ["string", "integer"]},
                                    "latency_penalty_pct": {
                                        "type": "number", "minimum": 0
                                    },
                                    "energy_penalty_pct": {
                                        "type": "number", "minimum": 0
                                    },
                                    "area_penalty_pct": {
                                        "type": "number", "minimum": 0
                                    },
                                },
                            },
                        },
                    },
                },
                "add_modules": {
                    "type": "array",
                    "items": {"$ref": "#/definitions/ModuleInstance"},
                },
                "remove_modules": {
                    "type": "array",
                    "items": {"type": "string", "pattern": _NAME},
                },
                "add_connections": {
                    "type": "array",
                    "items": {"$ref": "#/definitions/Connection"},
                },
                "remove_connections": {
                    "type": "array",
                    "items": {"$ref": "#/definitions/Connection"},
                },
                "mapping_hints": {"$ref": "#/definitions/MappingHints"},
            },
        },
        # v0.2 D2: narrow mapping_hints to op_type → stage → module_id | [module_id].
        "MappingHints": {
            "type": "object",
            "additionalProperties": {
                "type": "object",
                "additionalProperties": {
                    "oneOf": [
                        {"type": "string", "pattern": _NAME},
                        {
                            "type": "array",
                            "items": {"type": "string", "pattern": _NAME},
                            "minItems": 1,
                        },
                    ],
                },
            },
        },
        "Topology": {
            "type": "object",
            "required": ["type"],
            "properties": {
                "type": {
                    "type": "string",
                    "enum": ["single_die", "multi_die_2d", "multi_die_3d"],
                },
                "dies": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["id", "modules"],
                        "properties": {
                            "id": {"type": "string"},
                            "process_node": {"type": "string"},
                            "modules": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                        },
                    },
                },
                "inter_die": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "from_die": {"type": "string"},
                            "to_die": {"type": "string"},
                            "type": {
                                "type": "string",
                                "enum": ["wire", "tsv", "microbump"],
                            },
                            "latency_cycles": {"type": "integer"},
                            "bandwidth_gbps": {"type": "number"},
                        },
                    },
                },
            },
        },
        "Constraints": {
            "type": "object",
            "additionalProperties": {
                "type": "object",
                "properties": {
                    "min": {"type": "number"},
                    "max": {"type": "number"},
                },
            },
        },
    },
}
