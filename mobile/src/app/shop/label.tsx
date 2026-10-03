import { useQueryClient } from '@tanstack/react-query';
import { CameraView, useCameraPermissions } from 'expo-camera';
import { ImageManipulator, SaveFormat } from 'expo-image-manipulator';
import { router } from 'expo-router';
import { useRef, useState } from 'react';
import { StyleSheet, View } from 'react-native';

import { ApiError } from '../../api/client';
import { checkLabel } from '../../api/endpoints';
import type { Order, Verification } from '../../api/types';
import { bannerFor, EmptyState, OptionSelector, PhotoStepHeader, VerificationBanner } from '../../components/blocks';
import { ExampleLabel } from '../../components/Illustrations';
import { Button, Loading, Screen, Text } from '../../components/ui';
import { TextKey, useI18n } from '../../i18n';
import { keys, useOrders } from '../../lib/queries';
import { colors, radius } from '../../theme/tokens';

const RESULT_TEXT: Record<Verification['result'], [TextKey, TextKey]> = {
  verified: ['shop.labelGenuine', 'shop.labelGenuineBody'],
  not_prescribed: ['shop.labelNotPrescribed', 'shop.labelNotPrescribedBody'],
  mismatch: ['shop.labelNotPrescribed', 'shop.labelNotPrescribedBody'],
  not_registered: ['shop.labelNotRegistered', 'shop.labelNotRegisteredBody'],
  unreadable: ['shop.labelUnreadable', 'shop.labelUnreadableBody'],
};

/** S4: photograph the label of a collected product; the PCPB number is checked against the register and the prescription. */
export default function LabelCheck() {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const orders = useOrders();
  const [permission, requestPermission] = useCameraPermissions();
  const camera = useRef<CameraView>(null);
  const [ready, setReady] = useState(false);
  const [chosen, setChosen] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<Verification | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (orders.isPending) return <Loading label={t('common.loading')} />;
  const checkable = (orders.data ?? []).filter((o: Order) => o.status === 'collected' && !o.verifications.some((v) => v.type === 'label_check'));
  const orderId = chosen ?? (checkable.length === 1 ? checkable[0].id : null);

  if (result) {
    const [title, body] = RESULT_TEXT[result.result];
    const verified = result.result === 'verified';
    return (
      <Screen
        footer={
          verified ? (
            <Button label={t('reward.continue')} icon="star" onPress={() => router.replace('/shop/reward')} />
          ) : result.result === 'unreadable' ? (
            <Button label={t('common.retry')} icon="camera" onPress={() => setResult(null)} />
          ) : (
            <Button label={t('common.done')} onPress={() => router.replace('/shop')} />
          )
        }
      >
        <VerificationBanner tone={bannerFor(result.result)} title={t(title)} body={t(body)} />
        {result.product ? (
          <Text color={colors.inkMuted} style={{ textAlign: 'center' }}>
            {result.product.name} · {result.product.pcpb_reg_no}
          </Text>
        ) : result.detected_reg_no ? (
          <Text color={colors.inkMuted} style={{ textAlign: 'center' }}>
            {result.detected_reg_no}
          </Text>
        ) : null}
      </Screen>
    );
  }

  if (checkable.length === 0) {
    return (
      <Screen title={t('shop.checkLabel')} onBack={() => router.back()} backLabel={t('common.back')}>
        <EmptyState title={t('shop.checkLabel')} body={t('shop.labelNeedsCollection')} />
      </Screen>
    );
  }

  if (!orderId) {
    return (
      <Screen title={t('shop.checkLabel')} onBack={() => router.back()} backLabel={t('common.back')}>
        <OptionSelector
          question={t('shop.chooseOrder')}
          value={chosen}
          onChange={setChosen}
          options={checkable.map((o) => ({ value: o.id, label: `${o.product.name} · ${o.agrovet_name}` }))}
        />
      </Screen>
    );
  }

  if (!permission?.granted) {
    return (
      <Screen title={t('shop.checkLabel')} onBack={() => router.back()} backLabel={t('common.back')} footer={<Button label={t('check.allowCamera')} icon="camera" onPress={requestPermission} />}>
        <Text>{t('check.cameraPermission')}</Text>
      </Screen>
    );
  }

  const capture = async () => {
    if (!camera.current || !ready) return;
    setBusy(true);
    setError(null);
    try {
      const photo = await camera.current.takePictureAsync({ quality: 0.8, shutterSound: false });
      // The label service reads text best around 1200 px; it also keeps the upload small.
      const context = ImageManipulator.manipulate(photo.uri).resize(photo.width >= photo.height ? { width: 1400 } : { height: 1400 });
      const saved = await (await context.renderAsync()).saveAsync({ compress: 0.7, format: SaveFormat.JPEG });
      const verification = await checkLabel(orderId, saved.uri);
      queryClient.invalidateQueries({ queryKey: keys.orders });
      queryClient.invalidateQueries({ queryKey: keys.cases });
      queryClient.invalidateQueries({ queryKey: keys.rewards });
      queryClient.invalidateQueries({ queryKey: keys.me });
      setResult(verification);
    } catch (e) {
      setError(e instanceof ApiError && !e.offline ? e.message : t('common.errorBody'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Screen
      onBack={() => router.back()}
      backLabel={t('common.back')}
      scroll={false}
      footer={<Button label={t('check.takePhoto')} icon="camera" onPress={capture} loading={busy} disabled={!ready} />}
    >
      <PhotoStepHeader step={1} total={1} title={t('shop.labelTitle')} hint={t('shop.labelHint')} example={<ExampleLabel />} />
      {error ? <Text variant="bodyStrong" color={colors.danger}>⚠ {error}</Text> : null}
      <View style={styles.viewfinder}>
        <CameraView ref={camera} style={StyleSheet.absoluteFill} facing="back" onCameraReady={() => setReady(true)} />
        <View pointerEvents="none" style={styles.guide} />
        {busy ? (
          <View style={styles.checking}>
            <Text variant="bodyStrong" color={colors.inkOnDark}>
              {t('shop.labelChecking')}
            </Text>
          </View>
        ) : null}
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  viewfinder: { flex: 1, minHeight: 280, borderRadius: radius.lg, overflow: 'hidden', backgroundColor: '#000', alignItems: 'center', justifyContent: 'center' },
  guide: { width: '80%', aspectRatio: 1.6, borderWidth: 3, borderColor: colors.inkOnDark, borderStyle: 'dashed', borderRadius: radius.md },
  checking: { position: 'absolute', top: 0, right: 0, bottom: 0, left: 0, backgroundColor: colors.overlay, alignItems: 'center', justifyContent: 'center' },
});
