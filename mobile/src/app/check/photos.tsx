import { CameraView, useCameraPermissions } from 'expo-camera';
import { ImageManipulator, SaveFormat } from 'expo-image-manipulator';
import * as ImagePicker from 'expo-image-picker';
import { router, useLocalSearchParams } from 'expo-router';
import { ReactNode, useEffect, useRef, useState } from 'react';
import { Image, StyleSheet, View } from 'react-native';

import { ApiError } from '../../api/client';
import { getCase } from '../../api/endpoints';
import type { PhotoType, SymptomAnswers } from '../../api/types';
import { PhotoStepHeader } from '../../components/blocks';
import { ExampleLeaf, ExamplePlant, ExampleStemFruit } from '../../components/Illustrations';
import { Button, Gap, Screen, Text } from '../../components/ui';
import { TextKey, useI18n } from '../../i18n';
import { useMe } from '../../lib/queries';
import { keepFile, PendingReport, pendingReports, phoneIsOffline, saveReport, sendReport, uploadReportPhoto } from '../../offline/reports';
import { colors, radius, space } from '../../theme/tokens';

const STEPS: Array<{ type: PhotoType; title: TextKey; hint: TextKey; example: ReactNode }> = [
  { type: 'leaf', title: 'check.step1', hint: 'check.step1Hint', example: <ExampleLeaf /> },
  { type: 'plant', title: 'check.step2', hint: 'check.step2Hint', example: <ExamplePlant /> },
  { type: 'stem_fruit', title: 'check.step3', hint: 'check.step3Hint', example: <ExampleStemFruit /> },
];

// Big enough for the agrovet and the photo check (backend needs at least 480 px), small enough for data bundles.
const LONG_SIDE = 1600;

async function shrink(uri: string, width: number, height: number): Promise<string> {
  const context = ImageManipulator.manipulate(uri);
  if (Math.max(width, height) > LONG_SIDE) context.resize(width >= height ? { width: LONG_SIDE } : { height: LONG_SIDE });
  const image = await context.renderAsync();
  const saved = await image.saveAsync({ compress: 0.75, format: SaveFormat.JPEG });
  return saved.uri;
}

/** C2: three guided photos. Each is checked on upload when online; "Retake" if it is not clear. */
export default function Photos() {
  const { t } = useI18n();
  // localId: a queued report that needs a retake; caseId: a sent case whose photos must be retaken.
  const params = useLocalSearchParams<{ localId?: string; caseId?: string }>();
  const me = useMe();
  const [permission, requestPermission] = useCameraPermissions();
  const camera = useRef<CameraView>(null);
  const [ready, setReady] = useState(false);
  const [report, setReport] = useState<PendingReport | null>(null);
  const [step, setStep] = useState(0);
  const [preview, setPreview] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);

  // Resume a queued report that needs a retake, or start a new one.
  useEffect(() => {
    if (report || !me.data) return;
    (async () => {
      const existing = params.localId ? (await pendingReports()).find((r) => r.localId === params.localId) : undefined;
      if (existing) {
        setReport(existing);
        if (existing.retake) {
          setStep(STEPS.findIndex((s) => s.type === existing.retake!.type));
          setProblem(existing.retake.message || t('check.notClear'));
        }
        return;
      }
      const farm = me.data.farms[0];
      const fresh: PendingReport = {
        localId: `${Date.now()}`,
        createdAt: new Date().toISOString(),
        farm: farm?.id,
        photos: {},
      };
      if (params.caseId) {
        // Retake on a sent case: same case, same answers; new photos, then submit again.
        const sentCase = await getCase(params.caseId);
        Object.assign(fresh, {
          caseId: sentCase.id,
          answers: sentCase.symptom_answers as SymptomAnswers,
          answersSaved: true,
        });
      }
      await saveReport(fresh);
      setReport(fresh);
    })();
  }, [me.data, params.localId, params.caseId, report, t]);

  const current = STEPS[step];

  const capture = async () => {
    if (!camera.current || !ready) return;
    setBusy(true);
    try {
      const photo = await camera.current.takePictureAsync({ quality: 0.8, shutterSound: false });
      setPreview(await shrink(photo.uri, photo.width, photo.height));
      setProblem(null);
    } finally {
      setBusy(false);
    }
  };

  // A photo the farmer already has on the phone. The same check runs on upload as for camera photos.
  const pickFromGallery = async () => {
    setBusy(true);
    try {
      const picked = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ['images'], quality: 1 });
      if (picked.canceled) return;
      const asset = picked.assets[0];
      setPreview(await shrink(asset.uri, asset.width, asset.height));
      setProblem(null);
    } finally {
      setBusy(false);
    }
  };

  const usePhoto = async () => {
    if (!preview || !report) return;
    setBusy(true);
    try {
      const uri = keepFile(preview, `${current.type}.jpg`);
      let next: PendingReport = { ...report, photos: { ...report.photos, [current.type]: { uri, uploaded: false } } };
      await saveReport(next);
      const { report: updated, result } = await uploadReportPhoto(next, current.type);
      next = updated;
      setReport(next);
      if (result.status === 'retake') {
        setProblem(result.message || t('check.notClear'));
        setPreview(null);
        return;
      }
      if (result.status === 'failed') {
        // Online but the upload did not go through: keep the photo so "Use this photo" retries it.
        setUploadError(`${t('check.uploadFailed')} (${result.message})`);
        return;
      }
      setUploadError(null);
      setPreview(null);
      if (step < STEPS.length - 1) {
        setStep(step + 1);
      } else if (next.answers) {
        // A retake: the answers are already there, so send the report again now (or queue it).
        let caseId: string | null = null;
        try {
          caseId = await sendReport(next);
        } catch (error) {
          if (!(error instanceof ApiError && error.offline && (await phoneIsOffline()))) throw error;
        }
        router.replace({ pathname: '/check/sent', params: caseId ? { caseId } : { localId: next.localId } });
      } else {
        router.replace({ pathname: '/check/questions', params: { localId: next.localId } });
      }
    } catch (error) {
      setUploadError(`${t('check.uploadFailed')} (${error instanceof Error ? error.message : String(error)})`);
    } finally {
      setBusy(false);
    }
  };

  if (!permission) return null;
  if (!permission.granted && !preview) {
    return (
      <Screen
        title={t('check.photosTitle')}
        onBack={() => router.back()}
        backLabel={t('common.back')}
        footer={
          <>
            <Button label={t('check.allowCamera')} icon="camera" onPress={requestPermission} />
            <Button label={t('check.fromGallery')} icon="image" variant="secondary" onPress={pickFromGallery} loading={busy} />
          </>
        }
      >
        <Text>{t('check.cameraPermission')}</Text>
      </Screen>
    );
  }

  return (
    <Screen
      onBack={() => (step > 0 && !preview ? setStep(step - 1) : router.back())}
      backLabel={t('common.back')}
      scroll={false}
      footer={
        preview ? (
          <>
            <Button label={t('check.usePhoto')} icon="check" onPress={usePhoto} loading={busy} />
            <Button label={t('check.retake')} icon="refresh" variant="secondary" onPress={() => setPreview(null)} disabled={busy} />
          </>
        ) : (
          <>
            <Button label={t('check.takePhoto')} icon="camera" onPress={capture} loading={busy} disabled={!ready} />
            <Button label={t('check.fromGallery')} icon="image" variant="secondary" onPress={pickFromGallery} disabled={busy} />
          </>
        )
      }
    >
      <PhotoStepHeader step={step + 1} total={STEPS.length} title={t(current.title)} hint={t(current.hint)} example={current.example} />
      {problem ? (
        <View style={styles.problem} accessibilityRole="alert" accessibilityLiveRegion="assertive">
          <Text variant="bodyStrong" color={colors.warning}>
            ⚠ {t('check.notClear')}
          </Text>
          {problem !== t('check.notClear') ? <Text color={colors.warning}>{problem}</Text> : null}
        </View>
      ) : null}
      {uploadError ? (
        <Text variant="bodyStrong" color={colors.danger} accessibilityLiveRegion="assertive">
          ⚠ {uploadError}
        </Text>
      ) : null}
      <Gap size={space.sm} />
      <View style={styles.viewfinder}>
        {preview ? (
          <Image source={{ uri: preview }} style={StyleSheet.absoluteFill} resizeMode="cover" accessibilityLabel={t(current.title)} />
        ) : (
          <>
            <CameraView ref={camera} style={StyleSheet.absoluteFill} facing="back" onCameraReady={() => setReady(true)} />
            {/* Guide frame: where the leaf / plant / stem should be */}
            <View pointerEvents="none" style={[styles.guide, current.type === 'plant' ? styles.guideTall : styles.guideSquare]} />
          </>
        )}
        {busy && preview ? (
          <View style={styles.checking}>
            <Text variant="bodyStrong" color={colors.inkOnDark}>
              {t('check.checkingPhoto')}
            </Text>
          </View>
        ) : null}
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  viewfinder: { flex: 1, minHeight: 280, borderRadius: radius.lg, overflow: 'hidden', backgroundColor: '#000', alignItems: 'center', justifyContent: 'center' },
  guide: { borderWidth: 3, borderColor: colors.inkOnDark, borderStyle: 'dashed', borderRadius: radius.md },
  guideSquare: { width: '70%', aspectRatio: 1 },
  guideTall: { width: '55%', height: '88%' },
  problem: { backgroundColor: colors.warningSoft, borderColor: colors.warningIcon, borderWidth: 2, borderRadius: radius.md, padding: space.md, gap: space.xs },
  checking: { position: 'absolute', top: 0, right: 0, bottom: 0, left: 0, backgroundColor: colors.overlay, alignItems: 'center', justifyContent: 'center' },
});
