import React from 'react';
import { TextInput, View } from 'react-native';

import Txt from './Txt';

export default function Input({ label, ...props }) {
  const { colors } = undefined;
  return (
    <View style={{ marginBottom: 14 }}>
      {label ? <Txt muted style={{ marginBottom: 8 }}>{label}</Txt> : null}
      <TextInput
        {...props}
        placeholderTextColor='rgba(230,238,248,0.45)'
        style={[
          {
            backgroundColor: colors.input,
            color: colors.text,
            borderRadius: 24,
            paddingHorizontal: 16,
            height: 56,
            borderWidth: 1,
            borderColor: colors.border,
            fontSize: 18,
          },
          props.style,
        ]}
      />
    </View>
  );
}








