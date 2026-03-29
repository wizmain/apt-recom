import { useState } from 'react';
import { View, TextInput, TouchableOpacity, Text, StyleSheet, ScrollView } from 'react-native';

interface SearchBarProps {
  keywords: string[];
  onAddKeyword: (keyword: string) => void;
  onRemoveKeyword: (keyword: string) => void;
}

export default function SearchBar({ keywords, onAddKeyword, onRemoveKeyword }: SearchBarProps) {
  const [text, setText] = useState('');

  const handleSubmit = () => {
    const trimmed = text.trim();
    if (trimmed) {
      onAddKeyword(trimmed);
      setText('');
    }
  };

  return (
    <View style={styles.wrapper}>
      <View style={styles.inputRow}>
        <TextInput
          style={styles.input}
          value={text}
          onChangeText={setText}
          placeholder="지역명 또는 단지명 검색"
          placeholderTextColor="#9CA3AF"
          returnKeyType="search"
          onSubmitEditing={handleSubmit}
        />
        <TouchableOpacity style={styles.searchBtn} onPress={handleSubmit}>
          <Text style={styles.searchBtnText}>검색</Text>
        </TouchableOpacity>
      </View>
      {keywords.length > 0 && (
        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.tags}>
          {keywords.map(kw => (
            <View key={kw} style={styles.tag}>
              <Text style={styles.tagText}>{kw}</Text>
              <TouchableOpacity onPress={() => onRemoveKeyword(kw)}>
                <Text style={styles.tagClose}>✕</Text>
              </TouchableOpacity>
            </View>
          ))}
        </ScrollView>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  wrapper: {
    paddingHorizontal: 12,
    paddingTop: 8,
  },
  inputRow: {
    flexDirection: 'row',
    gap: 8,
  },
  input: {
    flex: 1,
    height: 42,
    backgroundColor: '#F9FAFB',
    borderRadius: 10,
    paddingHorizontal: 14,
    fontSize: 14,
    borderWidth: 1,
    borderColor: '#E5E7EB',
    color: '#111827',
  },
  searchBtn: {
    backgroundColor: '#3B82F6',
    borderRadius: 10,
    paddingHorizontal: 16,
    justifyContent: 'center',
  },
  searchBtnText: {
    color: '#FFFFFF',
    fontSize: 14,
    fontWeight: '600',
  },
  tags: {
    marginTop: 8,
    flexDirection: 'row',
  },
  tag: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#EFF6FF',
    borderRadius: 14,
    paddingHorizontal: 10,
    paddingVertical: 4,
    marginRight: 6,
    gap: 4,
  },
  tagText: {
    fontSize: 12,
    color: '#3B82F6',
    fontWeight: '500',
  },
  tagClose: {
    fontSize: 11,
    color: '#93C5FD',
    fontWeight: 'bold',
  },
});
