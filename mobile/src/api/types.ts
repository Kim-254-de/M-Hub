/** Shapes of the AgriSense API (backend/ OpenAPI schema at /api/schema/). Only what the app uses. */

export type Language = 'en' | 'sw' | 'ki';

export type TokenPair = { access: string; refresh: string };

export type Farm = {
  id: string;
  name?: string;
  latitude: string;
  longitude: string;
  size_acres: string;
  crops?: string[];
  created_at: string;
};

export type Me = {
  name: string;
  phone: string;
  language: Language;
  county: string;
  ward: string;
  notifications_enabled: boolean;
  points: number;
  support_whatsapp: string;
  farms: Farm[];
};

export type CaseStatus =
  | 'DRAFT'
  | 'REPORTED'
  | 'DIAGNOSING'
  | 'SECOND_OPINION'
  | 'DIAGNOSED'
  | 'UNKNOWN'
  | 'PRESCRIBED'
  | 'EXPIRED'
  | 'PURCHASED'
  | 'VERIFIED'
  | 'FLAGGED';

export type PhotoType = 'leaf' | 'plant' | 'stem_fruit';

export type CasePhoto = { id: string; type: PhotoType; image: string; width: number; height: number; created_at: string };

export type Case = {
  id: string;
  status: CaseStatus;
  farm: string | null;
  latitude: string | null;
  longitude: string | null;
  symptom_answers: Record<string, unknown>;
  photos: CasePhoto[];
  missing_photos: PhotoType[];
  detection: { ai_status: string | null; needs_retake: boolean; retake_reason: string | null; retake_message: string | null };
  disease: string | null;
  voice_note: string | null;
  created_at: string;
  submitted_at: string | null;
};

export type SymptomAnswers = {
  started: 'less_than_3_days' | '3_to_7_days' | '1_to_2_weeks' | 'over_2_weeks';
  share_affected: 'few' | 'some' | 'most';
  recent_weather: Array<'rainy' | 'humid' | 'hot_dry' | 'cold' | 'normal'>;
  already_sprayed: boolean;
  notes?: string;
};

export type Disease = { id: string; name: string; scientific_name: string; type: string };

export type AgrovetSummary = {
  id: string;
  name: string;
  phone: string;
  latitude: string;
  longitude: string;
  distance_km: number | null;
};

export type CaseDiagnosis = {
  case_id: string;
  status: CaseStatus;
  message: string | null;
  provisional: {
    kind: 'likely' | 'healthy' | 'unsure';
    disease: Disease | null;
    name: string | null;
    probability: number | null;
    message: string;
  } | null;
  safe_actions: string[];
  disease: Disease | null;
  disease_name: string | null;
  explanation: string;
  ai_evidence: { name: string; percent: number } | null;
  confidence: string | null;
  confirmed_by: string | null;
  ai_corrected: boolean | null;
  ai_corrected_message: string | null;
  reviewer: AgrovetSummary | null;
  similar_nearby: number | null;
};

export type CardProduct = {
  id: string;
  name: string;
  pcpb_reg_no: string;
  active_ingredients: string[];
  label_rate: string;
  phi_days: number | null;
  ppe_notes: string;
};

export type PrescriptionCard = {
  id: string;
  case: string;
  code: string;
  qr_payload: string;
  disease: string | null;
  approved_product: CardProduct | null;
  options: CardProduct[];
  quantity: string;
  safety_notes: string;
  phi_days: number | null;
  instructions: { language: string; dose: string; harvest: string; safety: string[]; label_notes: string };
  dose_packs: number | null;
  approved_by: string;
  expires_at: string;
  is_expired: boolean;
  created_at: string;
};

export type ProductSummary = { id: string; name: string; pcpb_reg_no: string; active_ingredients: string[]; phi_days: number | null };

export type StoreOffer = {
  store_item_id: string;
  agrovet_id: string;
  agrovet_name: string;
  agrovet_phone: string;
  latitude: string;
  longitude: string;
  distance_km: number | null;
  price_kes: number;
  product: ProductSummary;
};

export type Payment = {
  id: string;
  status: 'pending' | 'success' | 'failed' | 'review';
  amount_kes: number;
  phone: string;
  mpesa_receipt: string;
  result_desc: string;
  created_at: string;
  completed_at: string | null;
};

export type VerificationResult = 'verified' | 'mismatch' | 'not_registered' | 'not_prescribed' | 'unreadable';

export type Verification = {
  id: string;
  type: 'sale_match' | 'label_check';
  result: VerificationResult;
  message: string;
  product: ProductSummary | null;
  detected_reg_no: string;
  created_at: string;
};

export type Order = {
  id: string;
  prescription_code: string;
  agrovet: string;
  agrovet_name: string;
  product: ProductSummary;
  unit_price_kes: number;
  quantity: number;
  total_kes: number;
  payment_method: 'mpesa' | 'pay_at_shop';
  status: 'awaiting_payment' | 'reserved' | 'paid' | 'collected' | 'cancelled';
  paid_at: string | null;
  collected_at: string | null;
  cancelled_at: string | null;
  payments: Payment[];
  verifications: Verification[];
  created_at: string;
};

export type RewardEntry = {
  id: string;
  reason: 'verified_purchase' | 'case_reported' | 'follow_up' | 'referral' | 'redemption';
  points: number;
  created_at: string;
};

export type MyRewards = { balance: number; entries: RewardEntry[] };

export type CheckIn = {
  day: number;
  new_spots: 'spreading' | 'fewer' | 'stopped';
  share_affected: 'few' | 'some' | 'most';
  photo: string | null;
  notes: string;
  advice: string;
  created_at: string;
};

export type FollowUp = {
  case_id: string;
  can_record_spray: boolean;
  spray: {
    sprayed_at: string;
    product_id: string;
    product: string;
    amount_used: string;
    harvest_safe_from: string | null;
  } | null;
  schedule: Array<{ day: number; due_at: string; status: 'done' | 'due' | 'upcoming' | 'missed'; check_in: CheckIn | null }>;
  next_due_day: number | null;
  complete: boolean;
  expected: {
    product: string;
    enough_data: boolean;
    improved: number | null;
    reported: number | null;
    typical_day: number | null;
    response_rate: number | null;
    text: string;
  } | null;
};

export type Outbreak = { disease: Disease; name: string; count: number; ward: string; message: string };

export type Answer = { answer: string; language: string; blocked: boolean; available: boolean };

/** Error body from the API: {detail, code} or DRF field errors. */
export type ApiErrorBody = { detail?: string; code?: string; [field: string]: unknown };
