// Package store handles all PostgreSQL interactions for scribe.
// It wraps a pgxpool connection pool and exposes typed operations
// on the public.labs and public.companies tables.
package store

import (
	"context"
	"fmt"

	"github.com/jackc/pgx/v5/pgxpool"
)

// Store holds the connection pool shared across all store operations.
type Store struct {
	pool *pgxpool.Pool
}

// New opens a pgx connection pool and verifies connectivity with Ping.
// connString should be a full PostgreSQL URL:
//
//	postgres://user:pass@host:5432/dbname
func New(ctx context.Context, connString string) (*Store, error) {
	pool, err := pgxpool.New(ctx, connString)
	if err != nil {
		return nil, fmt.Errorf("create pgx pool: %w", err)
	}
	if err := pool.Ping(ctx); err != nil {
		pool.Close()
		return nil, fmt.Errorf("ping postgres: %w", err)
	}
	return &Store{pool: pool}, nil
}

// IsReady returns true when the pool can reach the database.
func (s *Store) IsReady(ctx context.Context) bool {
	return s.pool.Ping(ctx) == nil
}

// Close releases all pool connections.
func (s *Store) Close() {
	s.pool.Close()
}
