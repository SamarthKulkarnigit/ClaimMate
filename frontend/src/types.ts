export type Agent = 'intake' | 'coordinator' | 'damage' | 'policy' | 'cost' | 'auditor' | 'human' | 'finalize';
export type EventType = 'agent_start' | 'agent_end' | 'message' | 'send_back' | 'escalate' | 'interrupt' | 'done' | 'error';
export interface ClaimEvent { type: EventType; agent: Agent; ts: string; text: string; data: Record<string, unknown> }
export interface Photo { id: string; path: string; url?: string; exif_datetime?: string | null; phash?: string; duplicate_of?: string | null }
export interface Damage { part: string; side: string; severity: string; action: string; material: string; photo_ids: string[]; confidence: number }
export interface Coverage { part: string; status: 'covered' | 'not_covered' | 'partial'; clause_id: string; clause_quote: string; reason: string }
export interface EstimateLine { part: string; action: string; part_price: number; part_source_url: string; labour_low: number; labour_high: number; paint: number; material: string; dep_pct: number; dep_amount: number; payable_low: number; payable_high: number; clause_id: string; photo_ids: string[]; note: string }
export interface Finding { check: string; ok: boolean | null; detail: string; send_back_to?: string }
export interface ClaimState {
  claim_id: string; story: string; accident_date: string;
  vehicle: { make: string; model: string; reg_no: string; cc: number; reg_date: string; age_months: number };
  policy: { policy_no: string; start: string; end: string; idv: number; zero_dep: boolean; voluntary_deductible: number; pdf_path?: string };
  photos?: Photo[]; damages?: Damage[]; coverage?: Coverage[]; plate_read?: string | null;
  estimate?: { lines: EstimateLine[]; totals: { gross_low: number; gross_high: number; depreciation: number; deductible: number; payable_low: number; payable_high: number } };
  audit?: { status: 'pass' | 'fail' | 'escalate'; findings: Finding[] };
  retries?: number; next?: string; decision?: 'approved' | 'rejected' | null;
  escalation?: { reasons: string[] } | null;
  outputs?: { pdf_path?: string; email_text?: string; insurer_ref?: string; handoff?: boolean }; synthetic?: boolean;
}
export interface Demo { name: string; title: string; description: string }
