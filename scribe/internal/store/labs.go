package store

import (
	"context"
	"fmt"
	"time"

	"github.com/redhat-openshift-partner-labs/workers/scribe/internal/payload"
)

// InsertLab writes a new row into public.labs and returns the generated id.
//
// State is always forced to "intake_stored" — scribe is the authoritative
// writer for this initial state regardless of what the ETL placed in
// db_columns.state.
//
// updated_at has no database default; we always supply time.Now().UTC().
//
// companyID is nullable (the lab may exist before company linkage is
// complete); pass nil when the company could not be resolved.
func (s *Store) InsertLab(ctx context.Context, p *payload.NormalizedPayload, companyID *int) (int, error) {
	startDate, err := parseTimestamp(p.StartDate())
	if err != nil {
		return 0, fmt.Errorf("parse start_date: %w", err)
	}
	endDate, err := parseTimestamp(p.EndDate())
	if err != nil {
		return 0, fmt.Errorf("parse end_date: %w", err)
	}

	const insertSQL = `
		INSERT INTO public.labs (
			cluster_id,
			generated_name,
			state,
			cluster_name,
			openshift_version,
			cluster_size,
			company_name,
			company_id,
			request_type,
			partner,
			sponsor,
			cloud_provider,
			primary_first,
			primary_last,
			primary_email,
			secondary_first,
			secondary_last,
			secondary_email,
			region,
			always_on,
			project_name,
			lease_time,
			description,
			notes,
			start_date,
			end_date,
			hold,
			request_id,
			extras,
			updated_at
		) VALUES (
			$1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
			$11, $12, $13, $14, $15, $16, $17, $18, $19, $20,
			$21, $22, $23, $24, $25, $26, $27, $28, $29, $30
		)
		RETURNING id`

	var labID int
	err = s.pool.QueryRow(ctx, insertSQL,
		p.ClusterID(),        // $1  cluster_id
		p.GeneratedName(),    // $2  generated_name
		"intake_stored",      // $3  state — scribe-owned initial state
		p.ClusterName(),      // $4  cluster_name
		p.OpenShiftVersion(), // $5  openshift_version
		p.ClusterSize(),      // $6  cluster_size
		p.CompanyName(),      // $7  company_name
		companyID,            // $8  company_id (nullable *int)
		p.RequestType(),      // $9  request_type
		p.Partner(),          // $10 partner
		p.Sponsor(),          // $11 sponsor
		p.CloudProvider(),    // $12 cloud_provider
		p.PrimaryFirst(),     // $13 primary_first
		p.PrimaryLast(),      // $14 primary_last
		p.PrimaryEmail(),     // $15 primary_email
		p.SecondaryFirst(),   // $16 secondary_first
		p.SecondaryLast(),    // $17 secondary_last
		p.SecondaryEmail(),   // $18 secondary_email
		p.Region(),           // $19 region
		p.AlwaysOn(),         // $20 always_on
		p.ProjectName(),      // $21 project_name
		p.LeaseTime(),        // $22 lease_time
		p.Description(),      // $23 description
		p.Notes(),            // $24 notes
		startDate,            // $25 start_date
		endDate,              // $26 end_date
		p.Hold(),             // $27 hold
		nullableString(p.RequestID()), // $28 request_id (nullable)
		p.ExtrasJSON(),       // $29 extras
		time.Now().UTC(),     // $30 updated_at (no DB default)
	).Scan(&labID)
	if err != nil {
		return 0, fmt.Errorf("insert lab: %w", err)
	}
	return labID, nil
}

// parseTimestamp parses an ISO 8601 string into a time.Time.
// pgx will handle passing time.Time to a timestamp column correctly.
func parseTimestamp(s string) (time.Time, error) {
	if s == "" {
		return time.Time{}, fmt.Errorf("timestamp string is empty")
	}
	// Try RFC3339 first (handles the Z suffix from ETL output).
	t, err := time.Parse(time.RFC3339, s)
	if err == nil {
		return t, nil
	}
	// Fall back to the format emitted by Python's datetime.isoformat()
	// when there is a UTC offset but no Z.
	const isoFmt = "2006-01-02T15:04:05.999999999-07:00"
	t, err = time.Parse(isoFmt, s)
	if err == nil {
		return t, nil
	}
	return time.Time{}, fmt.Errorf("cannot parse %q as ISO 8601", s)
}

// nullableString returns nil when s is empty so pgx stores SQL NULL
// rather than an empty string for optional text columns.
func nullableString(s string) *string {
	if s == "" {
		return nil
	}
	return &s
}
