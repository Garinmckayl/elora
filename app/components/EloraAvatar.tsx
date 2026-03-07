import React from 'react';
import { View, Image, StyleSheet } from 'react-native';
import { useTheme } from '../src/theme';

// Pre-require the GIF assets so Metro bundles them
const AVATAR_GIFS: Record<string, any> = {
  listening: require('../assets/avatars/elora-happy.gif'),
  happy: require('../assets/avatars/elora-happy.gif'),
  thinking: require('../assets/avatars/elora-thinking.gif'),
  working: require('../assets/avatars/elora-working.gif'),
  speaking: require('../assets/avatars/elora-working.gif'),
};

interface Props {
  state?: string;
  size?: 'small' | 'medium' | 'large';
  animated?: boolean;
}

export default function EloraAvatar({ state = 'happy', size = 'medium', animated = true }: Props) {
  const { colors } = useTheme();
  const sizeMap = { small: 40, medium: 60, large: 100 };
  const avatarSize = sizeMap[size];
  const gifSource = AVATAR_GIFS[state] || AVATAR_GIFS.happy;

  if (animated && gifSource) {
    return (
      <View style={[
        styles.avatarContainer,
        {
          width: avatarSize,
          height: avatarSize,
          borderRadius: avatarSize / 2,
          borderColor: colors.gold,
          shadowColor: colors.gold,
          backgroundColor: colors.surface,
        }
      ]}>
        <Image
          source={gifSource}
          style={{
            width: avatarSize - 4,
            height: avatarSize - 4,
            borderRadius: (avatarSize - 4) / 2,
          }}
          resizeMode="cover"
        />
      </View>
    );
  }

  // Fallback to colored circle if no GIF or not animated
  return (
    <View style={[
      styles.avatarContainer,
      {
        width: avatarSize,
        height: avatarSize,
        borderRadius: avatarSize / 2,
        borderColor: colors.gold,
        shadowColor: colors.gold,
        backgroundColor: colors.goldLight,
      }
    ]} />
  );
}

const styles = StyleSheet.create({
  avatarContainer: {
    borderWidth: 2.5,
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.4,
    shadowRadius: 12,
    elevation: 6,
    alignItems: 'center',
    justifyContent: 'center',
    overflow: 'hidden',
  },
});
