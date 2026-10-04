/**
 * Crop reports survive bad network: everything the farmer captured is kept on the phone (photos in
 * the app's document folder, not the cache) and sent step by step when there is a connection.
 * A report is removed from the outbox only after the server accepts the submission.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import NetInfo from '@react-native-community/netinfo';
import { Directory, File, Paths } from 'expo-file-system';
import { Platform } from 'react-native';

import { ApiError } from '../api/client';
import { createCase, getCase, saveAnswers, submitCase, uploadPhoto, uploadVoiceNote } from '../api/endpoints';
import type { PhotoType, SymptomAnswers } from '../api/types';

const KEY = 'agrisense.outbox';

export type PendingReport = {
  localId: string;
  createdAt: string;
  farm?: string;
  latitude?: string;
  longitude?: string;
  caseId?: string; // set once the server has created the case
  photos: Partial<Record<PhotoType, { uri: string; uploaded: boolean }>>;
  answers?: SymptomAnswers;
  answersSaved?: boolean;
  voiceUri?: string;
  voiceUploaded?: boolean;
  submitted?: boolean;
  // Set when the server rejected a photo after the farmer went offline; they must retake it.
  retake?: { type: PhotoType; message: string };
};

async function readAll(): Promise<PendingReport[]> {
  const raw = await AsyncStorage.getItem(KEY);
  return raw ? (JSON.parse(raw) as PendingReport[]) : [];
}

async function writeAll(reports: PendingReport[]): Promise<void> {
  await AsyncStorage.setItem(KEY, JSON.stringify(reports));
}

export async function pendingReports(): Promise<PendingReport[]> {
  return (await readAll()).filter((r) => !r.submitted);
}

export async function saveReport(report: PendingReport): Promise<void> {
  const all = (await readAll()).filter((r) => r.localId !== report.localId);
  await writeAll([...all, report]);
}

export async function removeReport(localId: string): Promise<void> {
  const all = await readAll();
  const report = all.find((r) => r.localId === localId);
  if (report) deleteLocalFiles(report);
  await writeAll(all.filter((r) => r.localId !== localId));
}

/** Copy a captured file out of the cache so the system cannot delete it before it is sent. */
export function keepFile(uri: string, name: string): string {
  if (Platform.OS === 'web') return uri;
  const folder = new Directory(Paths.document, 'outbox');
  if (!folder.exists) folder.create();
  const target = new File(folder, `${Date.now()}_${name}`);
  new File(uri).copy(target);
  return target.uri;
}

function deleteLocalFiles(report: PendingReport) {
  if (Platform.OS === 'web') return;
  const uris = [...Object.values(report.photos).map((p) => p?.uri), report.voiceUri];
  for (const uri of uris) {
    try {
      if (uri && uri.includes('/outbox/')) new File(uri).delete();
    } catch {
      // Already gone; nothing to clean up.
    }
  }
}

/**
 * Send whatever is left of one report. Returns the case id once submitted. Throws ApiError when
 * offline (status 0) so the caller can keep it queued.
 */
export async function sendReport(report: PendingReport): Promise<string | null> {
  let current = { ...report };
  const persist = async (changes: Partial<PendingReport>) => {
    current = { ...current, ...changes };
    await saveReport(current);
  };

  if (!current.caseId) {
    const created = await createCase({ farm: current.farm, latitude: current.latitude, longitude: current.longitude });
    await persist({ caseId: created.id });
  }
  const caseId = current.caseId!;

  for (const type of ['leaf', 'plant', 'stem_fruit'] as PhotoType[]) {
    const photo = current.photos[type];
    if (!photo || photo.uploaded) continue;
    try {
      await uploadPhoto(caseId, type, photo.uri);
    } catch (error) {
      if (error instanceof ApiError && error.status === 422) {
        await persist({ retake: { type, message: String(error.body?.detail ?? '') } });
        return null; // the farmer must retake this photo before the report can go
      }
      throw error;
    }
    await persist({ photos: { ...current.photos, [type]: { ...photo, uploaded: true } }, retake: undefined });
  }

  if (current.answers && !current.answersSaved) {
    await saveAnswers(caseId, current.answers);
    await persist({ answersSaved: true });
  }
  if (current.voiceUri && !current.voiceUploaded) {
    await uploadVoiceNote(caseId, current.voiceUri);
    await persist({ voiceUploaded: true });
  }
  if (!current.answers) return null; // still being filled in

  try {
    await submitCase(caseId);
  } catch (error) {
    // The server may have accepted an earlier try whose answer never reached the phone.
    if (!(error instanceof ApiError) || error.offline || (await getCase(caseId)).status === 'DRAFT') throw error;
  }
  await removeReport(current.localId);
  return caseId;
}

export type PhotoUploadResult =
  | { status: 'uploaded' }
  | { status: 'retake'; message: string }
  | { status: 'queued' }
  | { status: 'failed'; message: string };

/** Only a phone with no connection queues work; a failure while online must be shown, not hidden. */
export async function phoneIsOffline(): Promise<boolean> {
  const state = await NetInfo.fetch();
  return state.isConnected === false || state.isInternetReachable === false;
}

/**
 * Upload one photo straight away when there is a connection, so a blurry or dark photo can be
 * retaken on the spot. Offline, the photo stays in the outbox and goes later.
 */
export async function uploadReportPhoto(report: PendingReport, type: PhotoType): Promise<{ report: PendingReport; result: PhotoUploadResult }> {
  let current = report;
  try {
    if (!current.caseId) {
      const created = await createCase({ farm: current.farm, latitude: current.latitude, longitude: current.longitude });
      current = { ...current, caseId: created.id };
      await saveReport(current);
    }
    const photo = current.photos[type]!;
    await uploadPhoto(current.caseId!, type, photo.uri);
    current = { ...current, photos: { ...current.photos, [type]: { ...photo, uploaded: true } }, retake: undefined };
    await saveReport(current);
    return { report: current, result: { status: 'uploaded' } };
  } catch (error) {
    if (error instanceof ApiError && error.status === 422) {
      return { report: current, result: { status: 'retake', message: String(error.body?.detail ?? '') } };
    }
    if (error instanceof ApiError && error.offline) {
      if (await phoneIsOffline()) return { report: current, result: { status: 'queued' } };
      return { report: current, result: { status: 'failed', message: error.message } };
    }
    throw error;
  }
}

/** Try every queued report; called when the phone comes back online, when the app opens and from "Send now". */
export async function flushOutbox(): Promise<{ sent: number; error: string | null }> {
  let sent = 0;
  let lastError: string | null = null;
  for (const report of await pendingReports()) {
    if (!report.answers || report.retake) continue; // unfinished, or needs the farmer
    try {
      if (await sendReport(report)) sent += 1;
    } catch (error) {
      lastError = error instanceof Error ? error.message : String(error);
      if (error instanceof ApiError && error.offline) break; // no answer; try later
    }
  }
  return { sent, error: lastError };
}
