import { create } from 'zustand';
import { persist } from 'zustand/middleware';

const useAuthStore = create(
  persist(
    (set, get) => ({
      user: null,
      token: null,
      isAuthenticated: false,

      setAuth: (user, token) => {
        set({
          user,
          token,
          isAuthenticated: true
        });
        localStorage.setItem('token', token);
      },

      updateUser: (userData) => {
        set(state => ({
          user: { ...state.user, ...userData }
        }));
      },

      logout: () => {
        set({
          user: null,
          token: null,
          isAuthenticated: false
        });
        localStorage.removeItem('token');
      },

      getToken: () => {
        return get().token || localStorage.getItem('token');
      }
    }),
    {
      name: 'auth-storage',
      partialPersist: ['token', 'user', 'isAuthenticated']
    }
  )
);

export default useAuthStore;
