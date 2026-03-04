import React from 'react';
import { View, Image, StyleSheet } from 'react-native';

// Pre-require the GIF assets so Metro bundles them
const AVATAR_GIFS: Record<string, any> = {
  listening: require('../assets/avatars/elora-happy.gif'),
  happy: require('../assets/avatars/elora-happy.gif'),
  thinking: require('../assets/avatars/elora-thinking.gif'),
  working: require('../assets/avatars/elora-working.gif'),
  speaking: require('../assets/avatars/elora-working.gif'),  // working GIF for speaking state
};

interface Props {
  state?: string;
  size?: 'small' | 'medium' | 'large';
  animated?: boolean;
}

export default function EloraAvatar({ state = 'listening', size = 'medium', animated = true }: Props) {
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
        }
      ]}>
        <Image
          source={gifSource}
          style={{
            width: avatarSize - 6,
            height: avatarSize - 6,
            borderRadius: (avatarSize - 6) / 2,
          }}
          resizeMode="cover"
        />
      </View>
    );
  }

  // Fallback to colored circle if no GIF or not animated
  const fallbackColors: Record<string, string> = {
    listening: '#FFB800',
    thinking: '#FF9500',
    working: '#FF6B00',
    happy: '#FFD400',
    speaking: '#FF8C00',
  };

  return (
    <View style={[
      styles.avatarContainer,
      {
        width: avatarSize,
        height: avatarSize,
        borderRadius: avatarSize / 2,
        backgroundColor: fallbackColors[state] || fallbackColors.listening,
      }
    ]} />
  );
}

const styles = StyleSheet.create({
  avatarContainer: {
    borderWidth: 2,
    borderColor: '#D4A853',
    shadowColor: '#D4A853',
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.6,
    shadowRadius: 8,
    elevation: 5,
    alignItems: 'center',
    justifyContent: 'center',
    overflow: 'hidden',
    backgroundColor: '#121829',
  },
});
