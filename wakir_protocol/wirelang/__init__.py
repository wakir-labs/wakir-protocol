# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Callandor GmbH and contributors
"""Wirelang Layer 0-1 reference helpers.

Consolidates the Apache-2.0 helpers from
``wakir-runtime/wirelang/builder/`` and ``wakir-runtime/wirelang/nats/``
under a single sub-package for Cut-2 (ADR-0062).

Public surface re-exports the
``wakir_protocol.wirelang.nats_subject_mapping`` builders/parsers
(deterministic NATS subject convention from
``docs/nats-subject-mapping-v1.md``) and the
``wakir_protocol.wirelang.frame_builder`` helper.
"""

from wakir_protocol.wirelang.frame_builder import *  # noqa: F401,F403
from wakir_protocol.wirelang.nats_subject_mapping import (  # noqa: F401
    RESERVED_DOMAINS,
    RESERVED_EVENT_TYPES,
    SubjectFormatError,
    SubjectV1,
    build_subject,
    federation_host_slug,
    parse_subject,
    persona_slug,
    roundtrip,
    schema_for_subject,
    tv_anchor,
    validate_consumer_filter,
    validate_stream_pattern,
)

__all__ = [
    "SubjectV1",
    "SubjectFormatError",
    "build_subject",
    "parse_subject",
    "roundtrip",
    "validate_stream_pattern",
    "validate_consumer_filter",
    "schema_for_subject",
    "persona_slug",
    "tv_anchor",
    "federation_host_slug",
    "RESERVED_DOMAINS",
    "RESERVED_EVENT_TYPES",
]
