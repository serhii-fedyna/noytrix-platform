import React from 'react';
import { Text } from 'react-native';

export default function Txt(props) {
  return <Text style={[{ color: '#fff' }, props.style]}>{props.children}</Text>;
}








