// Package health provides a lightweight HTTP server for Kubernetes liveness and
// readiness probes. Start it in the background before the worker's main consume
// loop so that the pod is only marked ready once the worker is connected.
package health

import (
	"context"
	"fmt"
	"log/slog"
	"net/http"
)

// Server serves /healthz (liveness) and /readyz (readiness) on the given port.
type Server struct {
	srv   *http.Server
	ready func() bool
}

// New creates a health server. The ready callback is called on every /readyz
// request; return true when the worker's external connections are established.
func New(port int, ready func() bool) *Server {
	s := &Server{ready: ready}

	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		fmt.Fprint(w, "ok")
	})
	mux.HandleFunc("/readyz", func(w http.ResponseWriter, r *http.Request) {
		if s.ready() {
			w.WriteHeader(http.StatusOK)
			fmt.Fprint(w, "ready")
		} else {
			w.WriteHeader(http.StatusServiceUnavailable)
			fmt.Fprint(w, "not ready")
		}
	})

	s.srv = &http.Server{
		Addr:    fmt.Sprintf(":%d", port),
		Handler: mux,
	}
	return s
}

// Start launches the HTTP server in a background goroutine. Errors are logged
// but do not crash the worker — a failed health server is not fatal.
func (s *Server) Start() {
	go func() {
		if err := s.srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			slog.Error("health server error", "error", err)
		}
	}()
}

// Stop gracefully shuts down the health server.
func (s *Server) Stop(ctx context.Context) {
	if err := s.srv.Shutdown(ctx); err != nil {
		slog.Error("health server shutdown error", "error", err)
	}
}
