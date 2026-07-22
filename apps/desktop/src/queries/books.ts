import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { api } from '@/lib/api'

/** Mirrors app/models/schemas.py BookRead (superseded later by generated api-types). */
export type BookType = 'story_book' | 'movie_script' | 'short_film_script' | 'single_scene'

export interface Book {
  id: string
  title: string
  book_type: BookType
  structure_template_id: string | null
  logline: string | null
  front_matter: Record<string, unknown> | null
  cover_image_id: string | null
  created_at: string
  updated_at: string
}

export interface BookCreateInput {
  title: string
  book_type: BookType
  logline?: string | null
  front_matter?: Record<string, unknown> | null
}

export interface BookUpdateInput {
  id: string
  title?: string | null
  logline?: string | null
  front_matter?: Record<string, unknown> | null
  structure_template_id?: string | null
  cover_image_id?: string | null
}

export interface BookConvertInput {
  id: string
  book_type: BookType
}

/** Lists all books (docs/02 Book CRUD). */
export function useBooks() {
  return useQuery({
    queryKey: ['books'],
    queryFn: () => api.get<Book[]>('/books'),
  })
}

/** Fetches a single book; disabled until an id is available. */
export function useBook(bookId: string | undefined) {
  return useQuery({
    queryKey: ['books', bookId],
    queryFn: () => api.get<Book>(`/books/${bookId}`),
    enabled: !!bookId,
  })
}

export function useCreateBook() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: BookCreateInput) => api.post<Book>('/books', input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['books'] })
      toast.success('Book created')
    },
    onError: () => toast.error('Could not create the book'),
  })
}

export function useUpdateBook() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...body }: BookUpdateInput) => api.patch<Book>(`/books/${id}`, body),
    onSuccess: (_book, variables) => {
      queryClient.invalidateQueries({ queryKey: ['books'] })
      queryClient.invalidateQueries({ queryKey: ['books', variables.id] })
      toast.success('Book updated')
    },
    onError: () => toast.error('Could not update the book'),
  })
}

export function useDeleteBook() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (bookId: string) => api.delete(`/books/${bookId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['books'] })
      toast.success('Book deleted')
    },
    onError: () => toast.error('Could not delete the book'),
  })
}

export function useConvertBook() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, book_type }: BookConvertInput) =>
      api.post<Book>(`/books/${id}/convert`, { book_type }),
    onSuccess: (_book, variables) => {
      queryClient.invalidateQueries({ queryKey: ['books'] })
      queryClient.invalidateQueries({ queryKey: ['books', variables.id] })
      toast.success('Book type converted')
    },
    onError: () => toast.error('Could not convert the book'),
  })
}
