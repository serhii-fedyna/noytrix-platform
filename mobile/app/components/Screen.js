import React from 'react';
import { View, StyleSheet } from 'react-native';

export default function Screen({ children }) {
  return <View style={styles.container}>{children}</View>;
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#0B1220', 
    padding: 16,
  },
});
















