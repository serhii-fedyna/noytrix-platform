import React from 'react';
import Txt from './Txt';

export function H1({ children, style }) {
  return <Txt style={[{ fontSize: 28, fontWeight: '800' }, style]}>{children}</Txt>;
}
export function H2({ children, style }) {
  return <Txt style={[{ fontSize: 20, fontWeight: '800' }, style]}>{children}</Txt>;
}








