# Spec Delta

## Purpose

Turns texts into vectors through any OpenAI-compatible embeddings endpoint
(llama-server, Ollama, vLLM, OpenAI, Jina, Voyage), with an identity that
keeps the embedding cache correct across machines and models.

## ADDED Requirements

### Requirement: OpenAI-compatible embeddings
The embedding adapter SHALL send `POST <base_url>/embeddings` with
`input` (a list of texts) and, when `prefilter.model` is set, `model`. It
SHALL return one vector per input text, in input order, ordering the
response by each item's `index`. A response with a different number of
vectors, or vectors of different lengths, SHALL fail the call.

#### Scenario: Order restored
- **WHEN** the server returns embeddings with indexes 1, 0
- **THEN** the first returned vector is the one with index 0

#### Scenario: Missing vector
- **WHEN** 3 texts are sent and the server returns 2 embeddings
- **THEN** the call fails with an error naming the provider and the counts

### Requirement: Batching
Texts SHALL be sent in batches of at most `prefilter.batch_size`. Batches
SHALL run concurrently up to the provider's concurrency limit, and the
result SHALL keep input order across batches.

#### Scenario: Two batches
- **WHEN** 40 texts are embedded with `batch_size = 32`
- **THEN** two requests are sent, with 32 and 8 texts, and 40 vectors return in input order

### Requirement: Base64 payloads
Requests SHALL ask for `encoding_format: "base64"`. A base64 embedding
SHALL be decoded as little-endian 32-bit floats; a list of numbers SHALL be
accepted as is. When a base64 request is answered with HTTP 400 or 422,
the adapter SHALL retry that batch once without base64 and SHALL use plain
floats for the rest of its life.

#### Scenario: Base64 decoded
- **WHEN** the server returns the base64 encoding of the floats 0.5 and -1.0
- **THEN** the vector is `[0.5, -1.0]`

#### Scenario: Server ignores base64
- **WHEN** the server returns float arrays despite the base64 request
- **THEN** the vectors are returned unchanged

#### Scenario: Server rejects base64
- **WHEN** the first base64 request is answered 400 and the retry without base64 answers 200
- **THEN** the call succeeds and later requests do not ask for base64

### Requirement: Model identity
The adapter SHALL report the model identity used for cache keys: the model
name the endpoint returns in its response (else the configured model, else
the base URL) and the vector dimension. When no embedding has been made
yet, asking for the identity SHALL embed one short text to learn it; the
identity SHALL then be kept for the adapter's lifetime.

#### Scenario: Reported model wins
- **WHEN** the profile sets `model = "embed"` and the endpoint answers with `model: "Qwen3-Embedding-0.6B"` and 1024-dimensional vectors
- **THEN** the identity is `Qwen3-Embedding-0.6B` with dimension 1024

#### Scenario: Identity learned once
- **WHEN** the identity is asked for twice before any embedding
- **THEN** one request is sent

### Requirement: Embedding usage
Each request SHALL record its `usage.prompt_tokens` (0 when absent) as
input tokens in the prefilter stage.

#### Scenario: Tokens recorded
- **WHEN** two batches report 300 and 100 prompt tokens
- **THEN** the ledger shows 400 input tokens and 2 requests for the embeddings provider
