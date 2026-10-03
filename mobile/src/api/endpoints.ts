/** One function per API call the app makes. */
import { api, filePart } from './client';
import type {
  Answer,
  Case,
  CaseDiagnosis,
  CasePhoto,
  Farm,
  FollowUp,
  Language,
  Me,
  MyRewards,
  Order,
  Outbreak,
  Payment,
  PhotoType,
  PrescriptionCard,
  StoreOffer,
  SymptomAnswers,
  TokenPair,
  Verification,
} from './types';

// --- Sign-up and login ---------------------------------------------------------------------

export const requestCode = (phone: string, language: Language) =>
  api<void>('/auth/otp/', { method: 'POST', body: { phone, language }, auth: false });

export const verifyCode = (phone: string, code: string) =>
  api<{ phone_token: string }>('/auth/otp/verify/', { method: 'POST', body: { phone, code }, auth: false });

export const register = (body: {
  phone: string;
  phone_token: string;
  pin: string;
  name: string;
  language: Language;
  consent: boolean;
}) => api<TokenPair>('/auth/register/', { method: 'POST', body, auth: false });

export const login = (phone: string, pin: string) =>
  api<TokenPair>('/auth/token/', { method: 'POST', body: { phone, pin }, auth: false });

// --- Profile and farm -------------------------------------------------------------------------

export const getMe = () => api<Me>('/me/');
export const updateMe = (body: Partial<Pick<Me, 'name' | 'language' | 'ward' | 'county' | 'notifications_enabled'>>) =>
  api<Me>('/me/', { method: 'PATCH', body });

export const createFarm = (body: { latitude: string; longitude: string; size_acres: string; crops: string[] }) =>
  api<Farm>('/farms/', { method: 'POST', body });
export const updateFarm = (id: string, body: Partial<Pick<Farm, 'latitude' | 'longitude' | 'size_acres' | 'crops'>>) =>
  api<Farm>(`/farms/${id}/`, { method: 'PATCH', body });

export const getRewards = () => api<MyRewards>('/rewards/');

// --- Check Crop ---------------------------------------------------------------------------------

export const getOutbreaks = () => api<Outbreak[]>('/alerts/nearby/');

export const createCase = (body: { farm?: string; latitude?: string; longitude?: string }) =>
  api<Case>('/cases/', { method: 'POST', body });

export function uploadPhoto(caseId: string, type: PhotoType, uri: string) {
  const form = new FormData();
  form.append('type', type);
  form.append('image', filePart(uri, `${type}.jpg`, 'image/jpeg'));
  return api<CasePhoto>(`/cases/${caseId}/photos/`, { method: 'POST', body: form });
}

export const saveAnswers = (caseId: string, answers: SymptomAnswers) =>
  api<Case>(`/cases/${caseId}/answers/`, { method: 'PUT', body: answers });

export function uploadVoiceNote(caseId: string, uri: string) {
  const form = new FormData();
  form.append('audio', filePart(uri, 'voice_note.m4a', 'audio/mp4'));
  return api<Case>(`/cases/${caseId}/voice-note/`, { method: 'POST', body: form });
}

export const submitCase = (caseId: string) => api<Case>(`/cases/${caseId}/submit/`, { method: 'POST' });

// --- My Cases -------------------------------------------------------------------------------

export const listCases = () => api<Case[]>('/cases/');
export const getCase = (id: string) => api<Case>(`/cases/${id}/`);
export const getDiagnosis = (id: string) => api<CaseDiagnosis>(`/cases/${id}/diagnosis/`);
export const getPrescription = (id: string) => api<PrescriptionCard>(`/cases/${id}/prescription/`);
export const getFollowUp = (id: string) => api<FollowUp>(`/cases/${id}/follow-up/`);

export const recordSpray = (id: string, sprayedAt: string) =>
  api<FollowUp>(`/cases/${id}/follow-up/spray/`, { method: 'POST', body: { sprayed_at: sprayedAt } });

export function addCheckIn(id: string, body: { day: number; new_spots: string; share_affected: string }) {
  const form = new FormData();
  form.append('day', String(body.day));
  form.append('new_spots', body.new_spots);
  form.append('share_affected', body.share_affected);
  return api<FollowUp>(`/cases/${id}/follow-up/check-ins/`, { method: 'POST', body: form });
}

export const askAdviser = (id: string, question: string) =>
  api<Answer>(`/cases/${id}/advice/`, { method: 'POST', body: { question } });

// --- Shop -------------------------------------------------------------------------------------------

export function storesFor(code: string, location?: { latitude: string; longitude: string }) {
  const query = location ? `?latitude=${location.latitude}&longitude=${location.longitude}` : '';
  return api<StoreOffer[]>(`/prescriptions/${encodeURIComponent(code)}/stores/${query}`);
}

export const createOrder = (body: {
  prescription_code: string;
  store_item_id: string;
  quantity: number;
  payment_method: 'mpesa' | 'pay_at_shop';
}) => api<Order>('/orders/', { method: 'POST', body });

export const listOrders = () => api<Order[]>('/orders/');
export const getOrder = (id: string) => api<Order>(`/orders/${id}/`);
export const payOrder = (id: string) => api<Payment>(`/orders/${id}/pay/`, { method: 'POST', body: {} });

export function checkLabel(orderId: string, uri: string) {
  const form = new FormData();
  form.append('photo', filePart(uri, 'label.jpg', 'image/jpeg'));
  return api<Verification>(`/orders/${orderId}/label-check/`, { method: 'POST', body: form });
}
