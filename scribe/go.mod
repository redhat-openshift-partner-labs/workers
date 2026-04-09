module github.com/redhat-openshift-partner-labs/workers/scribe

go 1.26

require (
	github.com/caarlos0/env/v11 v11.3.1
	github.com/jackc/pgx/v5 v5.7.2
	github.com/rabbitmq/amqp091-go v1.10.0
)

require (
	github.com/google/uuid v1.6.0 // indirect
	github.com/jackc/pgpassfile v1.0.0 // indirect
	github.com/jackc/pgservicefile v0.0.0-20240606120523-5a60cdf6a761 // indirect
	github.com/jackc/puddle/v2 v2.2.2 // indirect
	golang.org/x/crypto v0.31.0 // indirect
	golang.org/x/sync v0.10.0 // indirect
	golang.org/x/text v0.21.0 // indirect
)

// commons-go is resolved via the go.work workspace — no version needed here.
require github.com/redhat-openshift-partner-labs/workers/commons-go v0.0.0

replace github.com/redhat-openshift-partner-labs/workers/commons-go => ../commons-go
