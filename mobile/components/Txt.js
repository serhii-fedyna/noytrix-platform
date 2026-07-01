import React from 'react';
import { Text } from 'react-native';


export default function Txt({ children, style, muted=false, numberOfLines, ellipsizeMode }) {
  const { colors } = undefined;
  return (
    <Text
      numberOfLines={numberOfLines}
      ellipsizeMode={ellipsizeMode}
      style={[
        { color: muted ? colors.textMuted : colors.text, fontSize: 16 },
        style,
      ]}
    >
      {children}
    </Text>
  );
}








