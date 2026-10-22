import { render, screen } from '@testing-library/react'
import { expect, test } from 'vitest'

import { Markdown } from './Markdown'

test('paragraphs, bold, italic and lists', () => {
  render(<Markdown source={'A **bold** and *soft* word.\n\n- one\n- two\n\n1. first\n2. second'} />)
  expect(screen.getByText('bold').tagName).toBe('STRONG')
  expect(screen.getByText('soft').tagName).toBe('EM')
  expect(screen.getAllByRole('listitem')).toHaveLength(4)
  expect(screen.getByText('first').closest('ol')).not.toBeNull()
})

test('markup is shown as text and never becomes elements', () => {
  const { container } = render(<Markdown source={'<img src=x onerror=alert(1)> and <b>no</b>'} />)
  expect(container.querySelector('img')).toBeNull()
  expect(container.querySelector('b')).toBeNull()
  expect(container.textContent).toContain('<img src=x')
})
