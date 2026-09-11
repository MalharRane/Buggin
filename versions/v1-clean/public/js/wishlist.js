// CHANGE-04: a genuinely-working wishlist feature, new in this version.
const Wishlist = {
  KEY: 'buggin_wishlist',

  read() {
    try {
      const raw = localStorage.getItem(this.KEY);
      return raw ? JSON.parse(raw) : [];
    } catch (e) {
      return [];
    }
  },

  write(ids) {
    localStorage.setItem(this.KEY, JSON.stringify(ids));
  },

  has(id) {
    return this.read().includes(id);
  },

  toggle(id) {
    const ids = this.read();
    const idx = ids.indexOf(id);
    if (idx === -1) {
      ids.push(id);
      this.write(ids);
      return true;
    }
    ids.splice(idx, 1);
    this.write(ids);
    return false;
  },
};
