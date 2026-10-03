## MODIFIED Requirements

### Requirement: Embedding cache
Embeddings SHALL be cached by the SHA-256 of the text, the model name
reported by the embedding endpoint, and the vector dimension. A vector SHALL be reused
only when all three match. Storing a vector whose length differs from the
cache entry's dimension SHALL fail with an error naming both dimensions,
and nothing SHALL be written.

#### Scenario: Same text, same model
- **WHEN** a chunk is embedded in one run and the same text is embedded again with the same model and dimension
- **THEN** the second embedding comes from the cache and no request is sent for it

#### Scenario: Different model
- **WHEN** the endpoint reports a different model name
- **THEN** no cached vector from the old model is used

#### Scenario: Wrong dimension
- **WHEN** a 768-dimensional vector is stored under an identity with dimension 1024
- **THEN** storing fails with an error naming 768 and 1024 and no file is written
