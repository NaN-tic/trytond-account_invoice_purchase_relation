# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.model import fields
from trytond.pool import Pool, PoolMeta
from trytond.pyson import If, Eval, Bool

from sql import Cast
from sql.operators import Concat

__all__ = ['Invoice', 'InvoiceLine']

__metaclass__ = PoolMeta

_STATES = {
    'invisible': If(Bool(Eval('_parent_invoice')),
        ~Eval('_parent_invoice', {}).get('type')
            .in_(['in_invoice', 'in_credit_note']),
        ~Eval('invoice_type')
            .in_(['in_invoice', 'in_credit_note'])),
}


class Invoice():
    __name__ = 'account.invoice'
    in_shipments = fields.Function(
        fields.Many2Many('stock.shipment.in', None, None, 'Supplier Shipments',
            states={
                'invisible': Eval('type').in_(['out_invoice',
                    'out_credit_note', 'in_credit_note']),
                }), 'get_in_shipments', searcher='search_in_shipments')
    in_shipment_returns = fields.Function(
        fields.Many2Many('stock.shipment.in.return', None, None,
            'Supplier Return Shipments',
            states={
                'invisible': Eval('type').in_(['out_invoice',
                    'out_credit_note', 'in_invoice']),
                }),
        'get_in_shipment_returns', searcher='search_in_shipment_returns')

    def get_in_shipments(self, name):
        return list(set([s.id for l in self.lines if l.in_shipments
                        for s in l.in_shipments]))

    def get_in_shipment_returns(self, name):
        return list(set([s.id for l in self.lines if l.in_shipment_returns
                        for s in l.in_shipment_returns]))

    @classmethod
    def search_in_shipments(cls, name, clause):
        pool = Pool()
        InvoiceLine = pool.get('account.invoice.line')
        InvoiceLineStockMove = pool.get('account.invoice.line-stock.move')
        StockMove = pool.get('stock.move')
        Shipment = pool.get('stock.shipment.in')
        invoice_line = InvoiceLine.__table__()
        invoice_line_stock_move = InvoiceLineStockMove.__table__()
        stock_move = StockMove.__table__()

        clause = Shipment.search_rec_name(name, clause)
        tables, condition = Shipment.search_domain(clause)
        shipment = tables[None][0]
        _, shipment_type = StockMove.shipment.sql_type()
        query = (invoice_line
            .join(invoice_line_stock_move,
                condition=invoice_line.id ==
                invoice_line_stock_move.invoice_line)
            .join(stock_move,
                condition=invoice_line_stock_move.stock_move == stock_move.id)
            .join(shipment,
                condition=stock_move.shipment == Concat('stock.shipment.in,',
                    Cast(shipment.id, shipment_type)))
            .select(invoice_line.invoice,
                where=condition))
        return [('id', 'in', query)]

    @classmethod
    def search_in_shipment_returns(cls, name, clause):
        pool = Pool()
        InvoiceLine = pool.get('account.invoice.line')
        InvoiceLineStockMove = pool.get('account.invoice.line-stock.move')
        StockMove = pool.get('stock.move')
        Shipment = pool.get('stock.shipment.in.return')
        invoice_line = InvoiceLine.__table__()
        invoice_line_stock_move = InvoiceLineStockMove.__table__()
        stock_move = StockMove.__table__()

        clause = Shipment.search_rec_name(name, clause)
        tables, condition = Shipment.search_domain(clause)
        shipment = tables[None][0]
        _, shipment_type = StockMove.shipment.sql_type()
        query = (invoice_line
            .join(invoice_line_stock_move,
                condition=invoice_line.id ==
                invoice_line_stock_move.invoice_line)
            .join(stock_move,
                condition=invoice_line_stock_move.stock_move == stock_move.id)
            .join(shipment,
                condition=stock_move.shipment ==
                Concat('stock.shipment.in.return,',
                    Cast(shipment.id, shipment_type)))
            .select(invoice_line.invoice,
                where=condition))
        return [('id', 'in', query)]

    @classmethod
    def view_attributes(cls):
        return super(Invoice, cls).view_attributes() + [
            ('/form/notebook/page[@id="purchases"]', 'states', {
                    'invisible': ~Eval('type').in_(['in_invoice', 'in_credit_note']),
                    })]


class InvoiceLine():
    __name__ = 'account.invoice.line'
    purchase = fields.Function(fields.Many2One('purchase.purchase', 'Purchase',
            states=_STATES), 'get_purchase', searcher='search_purchase')
    in_shipments = fields.Function(fields.One2Many('stock.shipment.in', None,
            'Supplier Shipments', states=_STATES),
        'get_in_shipments', searcher='search_in_shipments')
    in_shipment_returns = fields.Function(
        fields.One2Many('stock.shipment.in.return', None,
            'Supplier Return Shipments', states=_STATES),
        'get_in_shipment_returns', searcher='search_in_shipment_returns')
    in_shipment_info = fields.Function(fields.Char('Supplier Shipment Info',
            states=_STATES), 'get_in_shipment_info')

    def get_purchase(self, name):
        PurchaseLine = Pool().get('purchase.line')
        if isinstance(self.origin, PurchaseLine):
            return self.origin.purchase.id

    @classmethod
    def search_purchase(cls, name, clause):
        pool = Pool()
        PurchaseLine = pool.get('purchase.line')

        invoice_line = cls.__table__()
        purchase_line = PurchaseLine.__table__()
        _, origin_type = cls.origin.sql_type()
        _, operator, value = clause
        Operator = fields.SQL_OPERATORS[operator]

        query = (invoice_line
            .join(purchase_line, 'LEFT',
                condition=(invoice_line.origin == Concat('purchase.line,',
                        Cast(purchase_line.id, origin_type)))
                )
            .select(invoice_line.id,
                where=Operator(purchase_line.purchase, value)
                )
            )
        return [('id', 'in', query)]

    def get_in_shipments_returns(model_name):
        "Computes the returns or shipments"
        def method(self, name):
            Model = Pool().get(model_name)
            shipments = set()
            for move in self.stock_moves:
                if isinstance(move.shipment, Model):
                    shipments.add(move.shipment.id)
            return list(shipments)
        return method

    get_in_shipments = get_in_shipments_returns('stock.shipment.in')
    get_in_shipment_returns = \
        get_in_shipments_returns('stock.shipment.in.return')

    @classmethod
    def search_in_shipments(cls, name, clause):
        pool = Pool()
        InvoiceLineStockMove = pool.get('account.invoice.line-stock.move')
        StockMove = pool.get('stock.move')
        Shipment = pool.get('stock.shipment.in')
        invoice_line_stock_move = InvoiceLineStockMove.__table__()
        stock_move = StockMove.__table__()

        clause = Shipment.search_rec_name(name, clause)
        tables, condition = Shipment.search_domain(clause)
        shipment = tables[None][0]
        _, shipment_type = StockMove.shipment.sql_type()
        query = (invoice_line_stock_move
            .join(stock_move,
                condition=invoice_line_stock_move.stock_move == stock_move.id)
            .join(shipment,
                condition=stock_move.shipment == Concat('stock.shipment.in,',
                    Cast(shipment.id, shipment_type)))
            .select(invoice_line_stock_move.invoice_line,
                where=condition))
        return [('id', 'in', query)]

    @classmethod
    def search_in_shipment_returns(cls, name, clause):
        pool = Pool()
        InvoiceLineStockMove = pool.get('account.invoice.line-stock.move')
        StockMove = pool.get('stock.move')
        Shipment = pool.get('stock.shipment.in.return')
        invoice_line_stock_move = InvoiceLineStockMove.__table__()
        stock_move = StockMove.__table__()

        clause = Shipment.search_rec_name(name, clause)
        tables, condition = Shipment.search_domain(clause)
        shipment = tables[None][0]
        _, shipment_type = StockMove.shipment.sql_type()
        query = (invoice_line_stock_move
            .join(stock_move,
                condition=invoice_line_stock_move.stock_move == stock_move.id)
            .join(shipment,
                condition=stock_move.shipment ==
                Concat('stock.shipment.in.return,',
                    Cast(shipment.id, shipment_type)))
            .select(invoice_line_stock_move.invoice_line,
                where=condition))
        return [('id', 'in', query)]

    def get_in_shipment_info(self, name):
        info = ','.join([s.code for s in self.in_shipments] +
            [s.code for s in self.in_shipment_returns])
        return info
