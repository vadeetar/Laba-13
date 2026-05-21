package main

import "testing"

func TestProcessTriageHighPriority(t *testing.T) {
	result := processTriage(TriageTask{
		ID:       "1",
		Patient:  "Иван",
		Symptoms: []any{"chest pain"},
	})
	if result.Priority != "HIGH" {
		t.Fatalf("expected HIGH, got %s", result.Priority)
	}
	if result.Specialty != "кардиолог" {
		t.Fatalf("expected кардиолог, got %s", result.Specialty)
	}
}

func TestProcessTriageNormal(t *testing.T) {
	result := processTriage(TriageTask{
		ID:       "2",
		Patient:  "Мария",
		Symptoms: "лёгкая простуда",
	})
	if result.Priority != "NORMAL" {
		t.Fatalf("expected NORMAL, got %s", result.Priority)
	}
}
