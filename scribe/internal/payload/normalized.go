// Package payload defines the structure of the intake.normalized message
// that the ETL worker produces and scribe consumes.
package payload

import "encoding/json"

// NormalizedPayload is the body of an intake.normalized envelope.
// The ETL worker validates and transforms raw Google Sheet data into
// this canonical form before publishing.
type NormalizedPayload struct {
	// DbColumns maps directly to public.labs column names. Every key
	// corresponds to a column the INSERT statement will populate.
	DbColumns map[string]any `json:"db_columns"`

	// Extras holds fields that have no dedicated DB column; they are
	// stored as JSON text in the public.labs extras column.
	Extras map[string]any `json:"extras"`

	// IsStandardConfig indicates whether the request meets the
	// auto-provisioning criteria evaluated by the ETL worker.
	IsStandardConfig bool `json:"is_standard_config"`
}

// getString retrieves a string value from a map, returning "" if the
// key is absent or the value is not a string.
func getString(m map[string]any, key string) string {
	v, ok := m[key]
	if !ok || v == nil {
		return ""
	}
	s, _ := v.(string)
	return s
}

// getBool retrieves a boolean value from a map, returning false if the
// key is absent or the value cannot be interpreted as bool.
func getBool(m map[string]any, key string) bool {
	v, ok := m[key]
	if !ok || v == nil {
		return false
	}
	b, _ := v.(bool)
	return b
}

// ExtrasJSON returns the Extras map serialised as a JSON string suitable
// for storage in the public.labs extras text column.
func (p *NormalizedPayload) ExtrasJSON() string {
	if len(p.Extras) == 0 {
		return "{}"
	}
	b, err := json.Marshal(p.Extras)
	if err != nil {
		return "{}"
	}
	return string(b)
}

// Field accessors — thin wrappers that keep the worker code readable
// and insulate it from map[string]any type assertions.

func (p *NormalizedPayload) ClusterID() string      { return getString(p.DbColumns, "cluster_id") }
func (p *NormalizedPayload) GeneratedName() string  { return getString(p.DbColumns, "generated_name") }
func (p *NormalizedPayload) ClusterName() string    { return getString(p.DbColumns, "cluster_name") }
func (p *NormalizedPayload) OpenShiftVersion() string {
	return getString(p.DbColumns, "openshift_version")
}
func (p *NormalizedPayload) ClusterSize() string  { return getString(p.DbColumns, "cluster_size") }
func (p *NormalizedPayload) CompanyName() string  { return getString(p.DbColumns, "company_name") }
func (p *NormalizedPayload) RequestType() string  { return getString(p.DbColumns, "request_type") }
func (p *NormalizedPayload) Partner() bool        { return getBool(p.DbColumns, "partner") }
func (p *NormalizedPayload) Sponsor() string      { return getString(p.DbColumns, "sponsor") }
func (p *NormalizedPayload) CloudProvider() string { return getString(p.DbColumns, "cloud_provider") }
func (p *NormalizedPayload) PrimaryFirst() string  { return getString(p.DbColumns, "primary_first") }
func (p *NormalizedPayload) PrimaryLast() string   { return getString(p.DbColumns, "primary_last") }
func (p *NormalizedPayload) PrimaryEmail() string  { return getString(p.DbColumns, "primary_email") }
func (p *NormalizedPayload) SecondaryFirst() string {
	return getString(p.DbColumns, "secondary_first")
}
func (p *NormalizedPayload) SecondaryLast() string {
	return getString(p.DbColumns, "secondary_last")
}
func (p *NormalizedPayload) SecondaryEmail() string {
	return getString(p.DbColumns, "secondary_email")
}
func (p *NormalizedPayload) Region() string      { return getString(p.DbColumns, "region") }
func (p *NormalizedPayload) AlwaysOn() bool      { return getBool(p.DbColumns, "always_on") }
func (p *NormalizedPayload) ProjectName() string { return getString(p.DbColumns, "project_name") }
func (p *NormalizedPayload) LeaseTime() string   { return getString(p.DbColumns, "lease_time") }
func (p *NormalizedPayload) Description() string { return getString(p.DbColumns, "description") }
func (p *NormalizedPayload) Notes() string       { return getString(p.DbColumns, "notes") }
func (p *NormalizedPayload) StartDate() string   { return getString(p.DbColumns, "start_date") }
func (p *NormalizedPayload) EndDate() string     { return getString(p.DbColumns, "end_date") }
func (p *NormalizedPayload) Hold() bool          { return getBool(p.DbColumns, "hold") }
func (p *NormalizedPayload) RequestID() string   { return getString(p.DbColumns, "request_id") }
