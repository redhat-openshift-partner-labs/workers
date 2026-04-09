package store

import (
	"context"
	"fmt"
)

// EnsureCompany returns the id of the company with the given name,
// creating it if it does not yet exist.
//
// The INSERT uses ON CONFLICT DO NOTHING so concurrent workers will not
// race on the unique company_name constraint. If the insert is a no-op
// (the row already existed) we fall through to the SELECT.
//
// updated_at has no database default so we always supply time.Now().
func (s *Store) EnsureCompany(ctx context.Context, companyName string) (int, error) {
	// Attempt insert; ignore conflict on the unique company_name index.
	const insertSQL = `
		INSERT INTO public.companies (company_name, updated_at)
		VALUES ($1, NOW())
		ON CONFLICT (company_name) DO NOTHING
		RETURNING id`

	var id int
	err := s.pool.QueryRow(ctx, insertSQL, companyName).Scan(&id)
	if err == nil {
		// Row was inserted — we have the new id.
		return id, nil
	}

	// pgx returns pgx.ErrNoRows when RETURNING yields nothing (conflict path).
	// Fall back to a plain SELECT to retrieve the existing id.
	const selectSQL = `SELECT id FROM public.companies WHERE company_name = $1`
	err = s.pool.QueryRow(ctx, selectSQL, companyName).Scan(&id)
	if err != nil {
		return 0, fmt.Errorf("lookup company %q: %w", companyName, err)
	}
	return id, nil
}
