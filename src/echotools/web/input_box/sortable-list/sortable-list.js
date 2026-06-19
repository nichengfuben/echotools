/**
 * SortableList — 可排序列表组件（带上下箭头 + 删除按钮）
 *
 * Usage:
 *   var list = new SortableList(container, {
 *     items: ['a', 'b', 'c'],
 *     renderItem: function(value, index) { return '<input value="' + value + '">'; },
 *     getItemValue: function(el, index) { return el.querySelector('input').value; },
 *     onChange: function(items) { ... },
 *     placeholder: 'No items',
 *   });
 *   list.setItems(['x', 'y']);
 *   list.getItems(); // ['x', 'y']
 */
(function(global) {
  'use strict';

  function SortableList(container, opts) {
    if (typeof container === 'string') container = document.querySelector(container);
    if (!container) throw new Error('SortableList: container not found');
    this._container = container;
    this._opts = opts || {};
    this._items = (opts && opts.items) ? opts.items.slice() : [];
    this._renderItem = (opts && opts.renderItem) || function(v) { return '<span>' + String(v) + '</span>'; };
    this._getItemValue = (opts && opts.getItemValue) || null;
    this._onChange = (opts && opts.onChange) || null;
    this._placeholder = (opts && opts.placeholder) || 'No items';
    this._render();
  }

  SortableList.prototype.setItems = function(items) {
    this._items = items.slice();
    this._render();
  };

  SortableList.prototype.getItems = function() {
    if (this._getItemValue) {
      var els = this._container.querySelectorAll('.sl-item');
      var result = [];
      for (var i = 0; i < els.length; i++) {
        var val = this._getItemValue(els[i], i);
        if (val !== null && val !== undefined) result.push(val);
      }
      return result;
    }
    return this._items.slice();
  };

  SortableList.prototype._render = function() {
    var self = this;
    var list = this._container;
    if (!this._items.length) {
      list.innerHTML = '<div class="sl-empty">' + this._placeholder + '</div>';
      return;
    }
    var html = '';
    for (var i = 0; i < this._items.length; i++) {
      var isFirst = (i === 0);
      var isLast = (i === this._items.length - 1);
      html += '<div class="sl-item" data-index="' + i + '">';
      html += '<div class="sl-controls">';
      html += '<button type="button" class="sl-btn sl-up' + (isFirst ? ' sl-disabled' : '') + '" data-action="up" data-index="' + i + '" title="上移"' + (isFirst ? ' disabled' : '') + '>&#9650;</button>';
      html += '<button type="button" class="sl-btn sl-down' + (isLast ? ' sl-disabled' : '') + '" data-action="down" data-index="' + i + '" title="下移"' + (isLast ? ' disabled' : '') + '>&#9660;</button>';
      html += '</div>';
      html += '<div class="sl-content">' + this._renderItem(this._items[i], i) + '</div>';
      html += '<button type="button" class="sl-btn sl-remove" data-action="remove" data-index="' + i + '" title="删除">&times;</button>';
      html += '</div>';
    }
    list.innerHTML = html;

    // Bind events via delegation
    list.onclick = function(e) {
      var btn = e.target.closest('[data-action]');
      if (!btn) return;
      e.preventDefault();
      e.stopPropagation();
      var action = btn.dataset.action;
      var idx = parseInt(btn.dataset.index);
      if (action === 'up' && idx > 0) {
        self._swap(idx, idx - 1);
      } else if (action === 'down' && idx < self._items.length - 1) {
        self._swap(idx, idx + 1);
      } else if (action === 'remove') {
        self._items.splice(idx, 1);
        self._render();
        self._fireChange();
      }
    };
  };

  SortableList.prototype._swap = function(a, b) {
    var tmp = this._items[a];
    this._items[a] = this._items[b];
    this._items[b] = tmp;
    this._render();
    this._fireChange();
  };

  SortableList.prototype._fireChange = function() {
    if (this._onChange) this._onChange(this.getItems());
  };

  global.SortableList = SortableList;
})(typeof window !== 'undefined' ? window : this);
