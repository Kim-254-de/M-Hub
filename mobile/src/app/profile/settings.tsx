import { useQueryClient } from '@tanstack/react-query';
import { router } from 'expo-router';
import { Linking, Switch, View } from 'react-native';

import { updateMe } from '../../api/endpoints';
import { OptionSelector } from '../../components/blocks';
import Icon from '../../components/Icon';
import { Button, Card, ListItem, Row, Screen, Text } from '../../components/ui';
import { Language, LANGUAGES, useI18n } from '../../i18n';
import { useAuth } from '../../lib/auth';
import { keys, useMe } from '../../lib/queries';
import { colors, space } from '../../theme/tokens';

/** P3: language, SMS updates, WhatsApp, help, log out. */
export default function Settings() {
  const { t, language, setLanguage } = useI18n();
  const { signOut } = useAuth();
  const queryClient = useQueryClient();
  const me = useMe();
  const whatsapp = me.data?.support_whatsapp;

  const changeLanguage = (next: Language) => {
    setLanguage(next);
    // The server sends SMS and advice in this language too.
    updateMe({ language: next }).then(() => queryClient.invalidateQueries()).catch(() => undefined);
  };

  const toggleSms = (value: boolean) => {
    queryClient.setQueryData(keys.me, me.data ? { ...me.data, notifications_enabled: value } : me.data);
    updateMe({ notifications_enabled: value }).catch(() => queryClient.invalidateQueries({ queryKey: keys.me }));
  };

  return (
    <Screen title={t('profile.settings')} onBack={() => router.back()} backLabel={t('common.back')}>
      <OptionSelector<Language>
        question={t('profile.language')}
        value={language}
        onChange={changeLanguage}
        options={LANGUAGES.map((code) => ({ value: code, label: t(`languages.${code}`) }))}
      />
      <Card>
        <Row style={{ justifyContent: 'space-between', minHeight: 56 }}>
          <Row style={{ flex: 1 }}>
            <Icon name="bell" color={colors.leaf} />
            <View style={{ flex: 1 }}>
              <Text variant="bodyStrong">{t('profile.notifications')}</Text>
              <Text color={colors.inkMuted}>{t('profile.notificationsHint')}</Text>
            </View>
          </Row>
          <Switch
            accessibilityLabel={t('profile.notifications')}
            value={me.data?.notifications_enabled ?? true}
            onValueChange={toggleSms}
            trackColor={{ true: colors.leaf, false: colors.borderStrong }}
            thumbColor={colors.surface}
            style={{ transform: [{ scale: 1.2 }] }}
          />
        </Row>
      </Card>
      <Card style={{ padding: 0 }}>
        {whatsapp ? (
          <ListItem
            icon="chat"
            label={t('profile.whatsapp')}
            detail={t('profile.whatsappHint', { number: whatsapp })}
            onPress={() => Linking.openURL(`https://wa.me/${whatsapp.replace(/\D/g, '')}`)}
          />
        ) : null}
        <ListItem
          icon="help"
          label={t('profile.help')}
          detail={whatsapp ? t('profile.helpBody', { number: whatsapp }) : undefined}
          onPress={whatsapp ? () => Linking.openURL(`tel:${whatsapp}`) : undefined}
        />
      </Card>
      <View style={{ gap: space.sm }}>
        <Button label={t('profile.logout')} icon="logout" variant="secondary" onPress={signOut} />
      </View>
    </Screen>
  );
}
